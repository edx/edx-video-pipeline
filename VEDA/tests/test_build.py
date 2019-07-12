"""
build test

"""

from __future__ import absolute_import
import sys
import unittest


class BuildTest(unittest.TestCase):

    def setUp(self):
        self.assertTrue(True)

    def test_defaults(self):
        self.assertTrue(True)


def main():
    unittest.main()

if __name__ == '__main__':
    sys.exit(main())
