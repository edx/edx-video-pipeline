import os
import sys
import unittest
from django.test import TestCase

"""
Test VEDA API

"""
sys.path.append(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)
)))
from control.veda_video_validation import Validation


class TestValidation(TestCase):
    """
    Test class for Validation
    """

    def setUp(self):

        self.videofile = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            'test_files',
            'OVTESTFILE_01.mp4'
        )
        self.VALID = Validation(
            videofile=self.videofile
        )

    @unittest.skipIf(
        'TRAVIS' in os.environ and os.environ['TRAVIS'] == 'true',
        'Skipping this test on Travis CI due to unavailability of required ffprobe version.'
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
