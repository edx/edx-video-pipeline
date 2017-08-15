
import os
import sys
import unittest
from django.test import TestCase
import requests
import ast
import yaml

"""
This is an API connection test
set to pass if instance_config.yaml is missing

"""
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from veda_file_ingest import VideoProto, VedaIngest

requests.packages.urllib3.disable_warnings()


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
        self.auth_yaml = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'veda_auth.yaml'
        )

    def test_file_ingest(self):
        if not os.path.exists(self.auth_yaml):
            self.assertTrue(self.VI.auth_dict is None)
            return None


def main():
    unittest.main()


if __name__ == '__main__':
    sys.exit(main())
