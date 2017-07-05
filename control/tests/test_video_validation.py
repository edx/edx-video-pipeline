import os
import sys
import unittest

"""
Test VEDA API

"""
sys.path.append(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)
)))
from veda_video_validation import Validation


class TestValidation(unittest.TestCase):

    def setUp(self):

        self.videofile = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            'test_files',
            'OVTESTFILE_01.mp4'
        )
        self.VALID = Validation(
            videofile=self.videofile
        )

    def test_validation(self):
        """
        Check a known file for validity
        """
        self.assertTrue(self.VALID.validate())


def main():
    unittest.main()

if __name__ == '__main__':
    sys.exit(main())
