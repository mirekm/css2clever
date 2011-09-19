import argparse, re
from pyparsing import (alphanums, OneOrMore, ZeroOrMore, Word, Group, Optional, 
                       cStyleComment)


class Css2Clever(object):
    SINGLE_SELECTOR = Word(alphanums + '.:#_-')
    SELECTOR = OneOrMore(
        SINGLE_SELECTOR
    )
    VALUE = Word(alphanums + ' (\'/,%#-."\\)' )
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
                        Word(alphanums + '-*') +
                        Word(':').suppress() +
                        OneOrMore(
                            VALUE
                        ) +
                        Optional(';').suppress())
                )) +
            Word('}').suppress()
        )
    ).ignore(cStyleComment)

    class Node(object):
        def __init__(self, id, ruleset, depth=0):
            self.id = id
            self.depth = depth
            self.ruleset = ruleset or {}
            self.children = []
            self.is_leaf = True

        def get_or_create(self, path, depth=0):
            id = path[0]
            #print 'Trying to find %s' % id
            path = path[1:]
            for child in self.children:
                if child.id == id:
                    #print 'Node %s found in %s' % (child.id, self.id)
                    if len(path):
                        return child.get_or_create(path, depth+1)
                    else:
                        return child
            child = Css2Clever.Node(id, None, depth)
            self.is_leaf = False
            #print 'New leaf %s created in %s' % (child.id, self.id)
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
            for child in sorted(self.children, key=lambda x: x.is_leaf):
                for p in child._get_next_path(path=not len(path)
                        and child.id or ("%s %s" % (path, child.id))):
                    yield p

        def traverse(self, depth=0):
            children = sorted(self.children, key=lambda child: child.id)
            # print 'Traversing %s at depth %s' % (self.id, depth)
            for child in children:
                yield child, depth
                for grandchild, d in child.traverse(depth=depth+1):
                    yield grandchild, d


    def __init__(self, css):
        self.styles = Css2Clever.Node('', None)
        self.raw = css
        self.formats = {}
        self.CSS_EXTENSIONS = [self._inline_block_extension,
                               self._css_fallbacks_extension]
        self._register_format('ccss', self.ccss)
        self._register_format('css', self.css)

    def _process_selector(self, selector, rules):
        #print 'Processing %s' % selector
        self.original_selectors_counter += 1
        pseudo = []
        for s in selector:
            parts = s.split(':')
            if len(parts)>1:
                pseudo += (parts[0], ':'+parts[1])
            else:
                pseudo += parts
        node = self.get_or_create(pseudo)
        for rule, value in rules:
            node.ruleset[rule] = value

    def _register_format(self, name, output):
        self.formats[name] = { 'output': output }

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

    def convert(self):
        parsed = self.CSS.parseString(self.raw)
        self.original_selectors_counter = 0
        for block in parsed:
            selector_group = block[0]
            for selector in selector_group:
                self._process_selector(selector, block[1])
        self._apply_extensions()
        return self.styles

    def get_or_create(self, path):
        return self.styles.get_or_create(path)

    def output(self, format='ccss'):
        return self.formats[format]['output']()

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
                ret += '\t%s: %s;\n' % (rule[0], rule[1]);
            ret += '}\n'
        return ret

    def ccss(self):
        ret = ''
        for node, depth in self.styles.traverse():
            tabs = ''.join(['\t' for x in xrange(depth)])
            ret += '%s%s:\n' % (tabs, node.id.startswith(':') and
                                '&'+node.id or node.id)
            for rdef, rval in sorted(node.ruleset.items(), key=lambda rule: rule[0]):
                # [-][a-zA-Z] require backticking
                if re.match('-[a-zA-Z]', rval):
                    rval = '`%s`' % rval
                ret += '%s\t%s: %s\n' % (tabs, rdef, rval)
        return ret


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
            description='Convert CSS to CleverCSS (and correct/enhance it).',
            epilog='by Mirumee Labs http://mirumee.com/github')
    parser.add_argument('-f', '--format',
            default='ccss',
            help='Supported output formats: ccss (default), css.')
    parser.add_argument('input',
            help='a css file to process')

    args = parser.parse_args()
    with open(args.input, "r") as f:
        css = f.read()
        converter = Css2Clever(css)
        converter.convert()
        print '/* Css2Clever by Mirumee Labs (http://mirumee/github) */'
        print '/* %d block(s) converted. */' % converter.original_selectors_counter
        print converter.output(args.format)
