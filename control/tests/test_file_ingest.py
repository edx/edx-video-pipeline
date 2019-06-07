
import ast
import os
import sys
import unittest

from django.test import TestCase
import urllib3

from control.veda_file_ingest import VedaIngest, VideoProto

"""
This is an API connection test
set to pass if instance_config.yaml is missing

"""
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class TestIngest(TestCase):

    def setUp(self):
        self.VP = VideoProto(
            s3_filename=None,
            client_title='OVTESTFILE_01',
            file_extension='mp4'
        )
        self.VI = VedaIngest(
            course_object=None,
            video_proto=self.VP
        )

    def test_file_ingest(self):
        pass

def main():
    unittest.main()


if __name__ == '__main__':
    sys.exit(main())
