
import os
import sys
import unittest

"""
Test upload processes

"""
sys.path.append(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)
)))

from veda_hotstore import Hotstore
from veda_file_ingest import VideoProto
from veda_env import *


class TestHotstore(unittest.TestCase):

    def setUp(self):
        VP = VideoProto()
        VP.veda_id = 'XXXXXXXX2014-V00TEST'
        self.upload_filepath = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            'test_files',
            'OVTESTFILE_01.mp4'
        )

        self.H1 = Hotstore(
            video_object=VP,
            upload_filepath=self.upload_filepath
        )

    def test_single_upload(self):
        if self.H1.auth_dict is None:
            self.assertTrue(self.H1.upload() is False)
            return None

        self.assertTrue(self.H1.upload())

    def test_multi_upload(self):
        if self.H1.auth_dict is None:
            self.assertTrue(self.H1.upload() is None)
            return None

        self.H1.auth_dict['multi_upload_barrier'] = 0
        self.assertTrue(self.H1.upload())


def main():
    unittest.main()


if __name__ == '__main__':
    sys.exit(main())
