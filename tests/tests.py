import unittest
from test import test_support

from css2clever import Css2Clever


class Css2CleverTest(unittest.TestCase):
    css_input = 'tests/test.css'
    css_output = 'tests/test_output.css'
    ccss_input = 'tests/test.ccss'
    ccss_output = 'tests/test_output.ccss'
    def setUp(self):
        with open(self.css_input, 'r') as f:
            self.raw_css = f.read()
        with open(self.ccss_input, 'r') as f:
            self.raw_ccss = f.read()

    def tearDown(self):
        pass

    def test_ccss_import_ccss_export(self):
        c = Css2Clever(self.raw_ccss)
        c.convert('ccss')
        output = c.output('ccss')
        with open(self.ccss_output, 'r') as f:
            test_output = f.read().strip()
            assert output == test_output

    def test_css_import_css_export(self):
        c = Css2Clever(self.raw_css)
        c.convert('css')
        output = c.output('css')
        with open(self.css_output, 'r') as f:
            test_output = f.read().strip()
            assert output == test_output

    def test_css_import_ccss_export(self):
        c = Css2Clever(self.raw_css)
        c.convert('css')
        output = c.output('ccss')
        with open(self.ccss_output, 'r') as f:
            test_output = f.read().strip()
            assert output == test_output

    def test_ccss_import_css_export(self):
        c = Css2Clever(self.raw_ccss)
        c.convert('ccss')
        output = c.output('css')
        with open(self.css_output, 'r') as f:
            test_output = f.read().strip()
            assert output == test_output

if __name__ == '__main__':
    test_support.run_unittest(Css2CleverTest)
