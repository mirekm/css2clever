#!/usr/bin/env python

import argparse, re
from pyparsing import (alphanums, OneOrMore, ZeroOrMore, Word, Group, Optional,
                       cStyleComment, indentedBlock, delimitedList, Forward,
                       LineEnd, Combine, White)


class Css2Clever(object):

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
        pseudo_separator = None
        # It needs to be evaluated against all paths in selectors list
        for s in selectors:
            if isinstance(s, basestring):
                pseudo_separator = s
                continue
            if pseudo_separator:
                s = s.asList()
                s[0] = pseudo_separator + s[0]
                pseudo_separator = None
            else:
                s = s.asList()
            p = path + s
            for c in content:
                if c.getName() == 'content':
                    for node in c:
                        self._process_ccss_block(node, depth=depth+1, path=p)
                else:
                    if c.getName() == 'properties':
                        self.get_or_create(p, c)

    def _process_css_block(self, selector, properties):
        #print 'Processing %s' % selector
        self.get_or_create(selector, properties)


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

    def make_css_parser(self):
        # CSS grammar
        def _process_class(string, location, tokens):
            '''
            Direct child and pseudo-selectors support
            '''
            # Direct child
            if tokens[0]=='>':
                process_class.is_direct = True
                tokens.pop()
                return
            if process_class.is_direct:
                tokens[0] = '> %s' % tokens[0]
                process_class.is_direct = False
            # Pseudo-selectors
            ret = tokens[0].split(':')
            if len(ret)>1:
                tokens[0] = ret[0]
                tokens.insert(1, ':' + ret[1])

        _process_class.is_direct = False;
        classchars = alphanums + '.:#_-*[]\'=">'
        CSS_SINGLE_CLASS = Word(classchars).setParseAction(_process_class)
        CSS_PROPERTY_VALUE = Word(alphanums + ' (\'/,%#-."\\)' )
        CSS_PROPERTY_NAME = Word(alphanums + '-*')
        CSS_PROPERTY = (CSS_PROPERTY_NAME +
                        Word(':').suppress() +
                        OneOrMore(CSS_PROPERTY_VALUE) + Optional(';').suppress())
        CSS_SELECTOR = OneOrMore(CSS_SINGLE_CLASS)
        CSS_SELECTOR_GROUP = Group(
            Group(CSS_SELECTOR) +
            ZeroOrMore(
                Group(Word(',').suppress() + CSS_SELECTOR)
            )
        )
        CSS = OneOrMore(
            Group(
                CSS_SELECTOR_GROUP +
                Word('{').suppress() +
                Group(ZeroOrMore(Group(CSS_PROPERTY))) +
                Word('}').suppress()
            )
        ).ignore(cStyleComment)
        return CSS

    def make_ccss_parser(self):
        # CleverCSS (CCSS) grammar
        def _process_class(string, location, tokens):
            '''
            Direct child and pseudo-selectors support
            '''
            tokens[0] = tokens[0].strip()


        _process_class.is_direct = False;

        indent_stack = [1]
        PROPERTY_NAME = Word(alphanums + '-*')
        PROPERTY_VALUE = Word(alphanums + ' (`\'/,%#-."\\)' )
        CCSS_PROPERTY = Group(PROPERTY_NAME +
                              Word(':').suppress() +
                              PROPERTY_VALUE +
                              LineEnd().suppress()
                        ).setResultsName('property')
        CCSS_BREAK = Word('&')
        CCSS_SINGLE_CLASS = Combine(
                                Optional(
                                    Combine(CCSS_BREAK.suppress() + Optional(White()) + Word('>')) |
                                    (CCSS_BREAK.suppress() + Word(':'))
                                ) + Optional(White()) +
                                Word(alphanums + '.#_-*[]\'="')
                            ).setParseAction(_process_class)
        CCSS_SELECTOR = Group(OneOrMore(CCSS_SINGLE_CLASS))
        CCSS_SELECTOR_GROUP = Group(delimitedList(CCSS_SELECTOR) +
                                    Word(':').suppress() +
                                    LineEnd().suppress()
                              ).setResultsName('selectors')
        CCSS_DEF = Forward()
        CCSS_DEF << (Group(
                        Optional(LineEnd()).suppress() +
                        CCSS_SELECTOR_GROUP +
                        indentedBlock(
                            OneOrMore(CCSS_PROPERTY).setResultsName('properties') |
                            OneOrMore(CCSS_DEF)
                        , indent_stack).setResultsName('nodes')
                    )).setResultsName('content')
        CCSS = OneOrMore(CCSS_DEF).ignore(cStyleComment)
        return CCSS

    def get_or_create(self, path, properties=[]):
        node = self.styles.get_or_create(path)
        for rule, value in properties:
            value = value.replace('`', '')
            if rule in self.NON_SQUASHING_RULES:
                values = node.ruleset.get(rule, [])
                values.append(value)
            else:
                values = [value]
            node.ruleset[rule] = values
        return node

    def from_ccss(self):
        parsed = self.make_ccss_parser().parseString(self.raw)
        for node in parsed:
            self._process_ccss_block(node)
        return self.styles

    def from_css(self):
        parsed = self.make_css_parser().parseString(self.raw)
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
                    selector.pop()
                selector.append(x)
                prev = s
            ret += '%s {\n' % ' '.join(selector)
            for rule in d[1]:
                for val in rule[1]:
                    ret += '%s%s: %s;\n' % (self.TAB, rule[0], val);
            ret += '}\n'
        return ('/* Css2Clever by Mirumee Labs (http://mirumee/github) */\n%s' %
                ret[:-1])

    def ccss(self):
        ret = ''
        need_break = [':', '>']
        for node, depth in self.styles.traverse():
            tabs = ''.join([self.TAB for x in xrange(depth)])
            ret += '%s%s:\n' % (tabs, (node.id.strip()[0] in need_break) and '&'+node.id or node.id)
            for rdef, rval in sorted(node.ruleset.items(),
                                     key=lambda rule: rule[0]):
                for val in rval:
                    # [-][a-zA-Z] require backticking
                    if re.match('-[a-zA-Z]', val):
                        val = '`%s`' % val
                    ret += '%s%s%s: %s\n' % (tabs, self.TAB, rdef, val)
        return ret[:-1]


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
    with open(args.input, 'r') as f:
        css = f.read()
        converter = Css2Clever(css, tab=args.indention_string)
        converter.convert(args.input_format)
        print converter.output(args.output_format)
