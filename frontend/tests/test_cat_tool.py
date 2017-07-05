
import os
import sys
import unittest

"""
A basic unittest for the "Course Addition Tool"

"""

sys.path.append(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
from course_validate import VEDACat


class TestVariables(unittest.TestCase):

    def setUp(self):
        self.VCT = VEDACat()

    def test_config(self):
        self.assertTrue(len(self.VCT.veda_model) > 0)

    def test_institution_valid(self):
        self.VCT.inst_code = '111'
        self.assertTrue(self.VCT.institution_name() == 'Error')


def main():
    unittest.main()

if __name__ == '__main__':
    sys.exit(main())
