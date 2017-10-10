"""
Test upload processes
"""

import os
import sys
from django.test import TestCase

from boto.s3.connection import S3Connection
from mock import PropertyMock, patch
from moto import mock_s3_deprecated
from VEDA import utils

from control.veda_file_ingest import VideoProto
from control.veda_hotstore import Hotstore

sys.path.append(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)
)))


CONFIG_DATA = utils.get_config('test_config.yaml')


class TestHotstore(TestCase):

    def setUp(self):
        video_proto = VideoProto()
        video_proto.veda_id = 'XXXXXXXX2014-V00TEST'
        self.upload_filepath = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            'test_files',
            'OVTESTFILE_01.mp4'
        )

        with patch.object(Hotstore, '_READ_AUTH', PropertyMock(return_value=lambda: CONFIG_DATA)):
            self.hotstore = Hotstore(
                video_object=video_proto,
                upload_filepath=self.upload_filepath,
                video_proto=video_proto
            )

        # do s3 mocking
        mock = mock_s3_deprecated()
        mock.start()
        conn = S3Connection()
        conn.create_bucket(CONFIG_DATA['veda_s3_hotstore_bucket'])
        self.addCleanup(mock.stop)

    def test_single_upload(self):
        """
        Verify S3 single part upload.
        """
        if self.hotstore.auth_dict is None:
            self.assertTrue(self.hotstore.upload() is False)
            return None

        self.hotstore.auth_dict['multi_upload_barrier'] = os.stat(self.upload_filepath).st_size + 1
        self.assertTrue(self.hotstore.upload())

    def test_multi_upload(self):
        """
        Verify S3 single multi-part upload.
        """
        if self.hotstore.auth_dict is None:
            self.assertTrue(self.hotstore.upload() is None)
            return None

        self.hotstore.auth_dict['multi_upload_barrier'] = 0
        self.assertTrue(self.hotstore.upload())
