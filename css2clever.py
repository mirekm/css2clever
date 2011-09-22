#!/usr/bin/env python

import argparse, re
from pyparsing import (alphanums, OneOrMore, ZeroOrMore, Word, Group, Optional,
                       cStyleComment, indentedBlock, delimitedList, Forward,
                       LineEnd, ParseException)


class Css2Clever(object):
    # CSS grammar
    SINGLE_SELECTOR = Word(alphanums + '.:#_-')
    SELECTOR = OneOrMore(
        SINGLE_SELECTOR
    )
    VALUE = Word(alphanums + ' (\'/,%#-."\\)' )
    PROPERTY = Word(alphanums + '-*')
    SELECTOR_GROUP = Group(
        Group(SELECTOR) +
            ZeroOrMore(
                Group(Word(',').suppress() +
                SELECTOR)
            )
    )
    CSS = OneOrMore(
        Group(
            SELECTOR_GROUP +
            Word('{').suppress() +
            Group(
                ZeroOrMore(
                    Group(
                        PROPERTY +
                        Word(':').suppress() +
                        OneOrMore(
                            VALUE
                        ) +
                        Optional(';').suppress())
                )) +
            Word('}').suppress()
        )
    ).ignore(cStyleComment)

    #CleverCSS (CCSS) gramma
    indent_stack = [1]
    PROPERTY_NAME = Word(alphanums + '-*')
    PROPERTY_VALUE = Word(alphanums + ' (\'/,%#-."\\)' )
    CCSS_PROPERTY = Group(PROPERTY_NAME +
                          Word(':').suppress() +
                          PROPERTY_VALUE +
                          LineEnd().suppress()
                    ).setResultsName('property')
    CCSS_SINGLE_CLASS = Word(alphanums + '.#_-')
    CCSS_SELECTOR = Group(OneOrMore(CCSS_SINGLE_CLASS))
    CCSS_SELECTOR_GROUP = Group(delimitedList(CCSS_SELECTOR) +
                                Word(':').suppress() +
                                LineEnd().suppress()
                          ).setResultsName('selectors')
    CCSS_DEF = Forward()
    CCSS_DEF << (Group(
                    CCSS_SELECTOR_GROUP +
                    indentedBlock(
                        OneOrMore(CCSS_PROPERTY).setResultsName('properties') |
                        OneOrMore(CCSS_DEF)
                    , indent_stack).setResultsName('nodes')
                )).setResultsName('content')
    CCSS = OneOrMore(CCSS_DEF).ignore(cStyleComment)


    class Node(object):
        def __init__(self, id, ruleset, depth=0):
            self.id = id
            self.depth = depth
            self.ruleset = ruleset or {}
            self.children = []

        def get_or_create(self, path, depth=0):
            id = path[0]
            path = path[1:]
            for child in self.children:
                if child.id == id:
                    if len(path):
                        return child.get_or_create(path, depth+1)
                    else:
                        return child
            child = Css2Clever.Node(id, None, depth)
            self.children.append(child)
            self.children.sort(key=lambda child: child.id)
            if len(path):
                return child.get_or_create(path)
            return child

        def paths(self):
            return self._get_next_path(path=self.id)

        def _get_next_path(self, path=''):
            if len(self.ruleset.items()):
                new_def = [(key, value) for key, value in 
                        sorted(self.ruleset.items(), key=lambda rule: rule[0])]
                yield [path.split(' '), new_def]
            for child in self.children:
                for p in child._get_next_path(path=not len(path)
                        and child.id or ("%s %s" % (path, child.id))):
                    yield p

        def traverse(self, depth=0):
            children = sorted(self.children, key=lambda child: child.id)
            for child in children:
                yield child, depth
                for grandchild, d in child.traverse(depth=depth+1):
                    yield grandchild, d


    def __init__(self, css, tab='\t'):
        self.styles = Css2Clever.Node('', None)
        self.raw = css
        self.formats = {}
        self.original_selectors_counter = 0
        self.TAB = tab
        self.NON_SQUASHING_RULES = ['background']
        self.CSS_EXTENSIONS = [self._inline_block_extension,
                               self._css_fallbacks_extension]
        self._register_format('ccss', output=self.ccss, input=self.from_ccss)
        self._register_format('css', output=self.css, input=self.from_css)

    def _process_ccss_block(self, block, depth=0, path=[]):
        selectors = block[0]
        content = block[1]
        # It needs to be evaluated against all paths in selectors list
        for s in selectors:
            p = path + s.asList()
            for c in content:
                #if not isinstance(c, basestring):
                if c.getName() == 'content':
                    for node in c:
                        self._process_ccss_block(node, depth=depth+1, path=p)
                else:
                    if c.getName() == 'properties':
                        self.get_or_create(p, c)

    def _process_css_block(self, selector, properties):
        #print 'Processing %s' % selector
        self.original_selectors_counter += 1
        pseudo = []
        for s in selector:
            parts = s.split(':')
            if len(parts)>1:
                pseudo += (parts[0], ':'+parts[1])
            else:
                pseudo += parts
        self.get_or_create(pseudo, properties)


    def _register_format(self, name, output=None, input=None):
        self.formats[name] = { 'output': output, 'input': input }

    def _apply_extensions(self):
        for node in self.styles.traverse():
            for extension in self.CSS_EXTENSIONS:
                extension(node)

    def _inline_block_extension(self, node):
        node, depth = node[0], node[1]
        for rule, value in node.ruleset.items():
            if value == 'inline-block':
                node.ruleset['*display'] = 'inline'
                node.ruleset['zoom'] = '1'

    def _css_fallbacks_extension(self, node):
        node, depth = node[0], node[1]
        need_fallback = ['box-shadow', 'text-shadow', 'border-radius']
        fallback_mapping = [['-moz-box-shadow', '-webkit-box-shadow'],
                            ['-moz-text-shadow', '-webkit-text-shadow'],
                            ['-moz-border-radius', '-webkit-border-radius']]
        for rule, value in node.ruleset.items():
            n = xrange(len(need_fallback))
            for i in n:
                if need_fallback[i] == rule:
                    for f in fallback_mapping[i]:
                        node.ruleset[f] = value

    def get_or_create(self, path, properties=[]):
        node = self.styles.get_or_create(path)
        for rule, value in properties:
            if rule in self.NON_SQUASHING_RULES:
                values = node.ruleset.get(rule, [])
                values.append(value)
            else:
                values = [value]
            node.ruleset[rule] = values
        return node

    def from_ccss(self):
        parsed = self.CCSS.parseString(self.raw)
        for node in parsed:
            self._process_ccss_block(node)
        return self.styles

    def from_css(self):
        parsed = self.CSS.parseString(self.raw)
        self.original_selectors_counter = 0
        for block in parsed:
            selector_group = block[0]
            for selector in selector_group:
                self._process_css_block(selector, block[1])
        return self.styles

    def convert(self, format):
        f = self.formats.get(format, None)
        convert = f.get('input', None)
        if convert:
            convert()
            self._apply_extensions()
            return self.styles

    def output(self, format='ccss'):
        f = self.formats.get(format, None)
        output = f.get('output', None)
        if output:
            return output()

    def css(self):
        ret = ''
        for d in self.styles.paths():
            selector = []
            prev = ''
            for s in d[0]:
                x = s
                if s.startswith(':'):
                    x = prev+s
                selector.append(x)
                prev = s
            ret += '%s {\n' % ' '.join(selector)
            for rule in d[1]:
                ret += '%s%s: %s;\n' % (self.TAB, rule[0], ' '.join(rule[1]));
            ret += '}\n'
        return ('/* Css2Clever by Mirumee Labs (http://mirumee/github) */\n' +
                 '/* %d block(s) converted. */\n%s'
                 % (converter.original_selectors_counter, ret))

    def ccss(self):
        ret = ''
        for node, depth in self.styles.traverse():
            tabs = ''.join([self.TAB for x in xrange(depth)])
            ret += '%s%s:\n' % (tabs, node.id.startswith(':') and
                                '&'+node.id or node.id)
            for rdef, rval in sorted(node.ruleset.items(),
                                     key=lambda rule: rule[0]):
                for val in rval:
                    # [-][a-zA-Z] require backticking
                    if re.match('-[a-zA-Z]', val):
                        val = '`%s`' % val
                    ret += '%s%s%s: %s\n' % (tabs, self.TAB, rdef, val)
        return ret


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
            description='Convert CSS to CleverCSS (and correct/enhance it).',
            epilog='by Mirumee Labs http://mirumee.com/github')
    parser.add_argument('-o', '--output-format',
            default='ccss',
            help='Supported output formats: ccss (default), css.')
    parser.add_argument('-t', '--indention-string',
            default='\t',
            help='String representing single tab')
    parser.add_argument('-i', '--input-format',
            default='css',
            help='Supported input formats: css (default), ccss.')
    parser.add_argument('input',
            help='a css file to process')

    args = parser.parse_args()
    with open(args.input, "r") as f:
        css = f.read()
        converter = Css2Clever(css, tab=args.indention_string)
        converter.convert(args.input_format)
        print converter.output(args.output_format)
