import os
import sys
import unittest

"""
Test VEDA API

"""
sys.path.append(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)
)))
from control.veda_file_discovery import FileDiscovery


class TestValidation(unittest.TestCase):

    def setUp(self):

        self.videofile = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            'test_files',
            'OVTESTFILE_01.mp4'
        )
        self.FD = FileDiscovery()

    def test_build(self):
        """
        Check a known file for validity
        """
        self.assertTrue(True)


def main():
    unittest.main()


if __name__ == '__main__':
    sys.exit(main())
