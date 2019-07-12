
from __future__ import absolute_import
import os
import sys
import unittest
from django.test import TestCase

"""
A basic unittest for the "Course Addition Tool"

"""

sys.path.append(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
from control.veda_utils import Report


class TestReporting(TestCase):

    def setUp(self):
        self.R = Report(
            status='Complete',
            upload_serial="4939d60a60",
            youtube_id='TEST'
        )

    def test_conn(self):
        if self.R.auth_dict is None:
            self.assertTrue(True)
            return None
        self.R.upload_status()


def main():
    unittest.main()

if __name__ == '__main__':
    sys.exit(main())
