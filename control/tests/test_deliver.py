"""
Veda Delivery unit tests
"""

import os
import unittest

from django.test import TestCase

import responses
from control.veda_deliver import VedaDelivery
from control.veda_file_ingest import VideoProto
from mock import PropertyMock, patch
from moto import mock_s3_deprecated
from VEDA.utils import get_config
from VEDA_OS01.models import URL, Course, Destination, Encode, Video

CONFIG_DATA = get_config('test_config.yaml')


class VedaDeliverRunTest(TestCase):
    """
    Deliver Run Tests
    """
    def setUp(self):
        self.veda_id = 'XXXXXXXX2014-V00TES1'
        self.encode_profile = 'hls'
        self.course = Course.objects.create(
            institution='XXX',
            edx_classid='XXXXX',
            course_name=u'Intro to VEDA',
            local_storedir=u'This/Is/A/testID'
        )
        self.video = Video.objects.create(
            inst_class=self.course,
            edx_id=self.veda_id,
            client_title='Test Video',
            video_orig_duration='00:00:10.09',  # This is known
            pk=1
        )
        self.destination = Destination.objects.create(
            destination_name='TEST'
        )
        self.encode = Encode.objects.create(
            encode_destination=self.destination,
            profile_active=True,
            encode_suffix='HLS',
            product_spec=self.encode_profile,
            encode_filetype='HLS'
        )
        self.deliver_instance = VedaDelivery(
            veda_id=self.veda_id,
            encode_profile=self.encode_profile,
            CONFIG_DATA=CONFIG_DATA
        )

    @patch('control.veda_val.VALAPICall._AUTH', PropertyMock(return_value=lambda: CONFIG_DATA))
    @patch('control.veda_val.OAuthAPIClient.request')
    @responses.activate
    def test_run(self, _):
        """
        Test of HLS run-through function
        """
        # VAL Patching
        responses.add(
            responses.GET,
            CONFIG_DATA['val_api_url'] + '/XXXXXXXX2014-V00TES1',
            status=200,
            json={'error': 'null', 'courses': [], 'encoded_videos': []}
        )
        responses.add(responses.PUT, CONFIG_DATA['val_api_url'] + '/XXXXXXXX2014-V00TES1', status=200)
        self.VP = VideoProto(
            client_title='Test Video',
            veda_id=self.veda_id
        )
        self.encoded_file = '{file_name}_{suffix}.{ext}'.format(
            file_name=self.veda_id,
            suffix=self.encode.encode_suffix,
            ext=self.encode.encode_filetype
        )

        self.deliver_instance.run()
        # Assertions
        self.assertEqual(self.deliver_instance.video_proto.val_id, 'XXXXXXXX2014-V00TES1')
        self.assertEqual(self.deliver_instance.video_proto.veda_id, self.veda_id)
        self.assertEqual(self.deliver_instance.video_proto.duration, 10.09)
        self.assertEqual(self.deliver_instance.video_proto.s3_filename, None)

        self.assertEqual(self.deliver_instance.encode_query, self.encode)
        self.assertEqual(self.deliver_instance.encoded_file, '/'.join((self.veda_id, self.veda_id + '.m3u8')))
        self.assertEqual(self.deliver_instance.status, 'Complete')
        self.assertEqual(
            self.deliver_instance.endpoint_url,
            '/'.join((
                CONFIG_DATA['edx_cloudfront_prefix'],
                self.veda_id,
                self.veda_id + '.m3u8'
            ))
        )

    @mock_s3_deprecated
    def test_intake(self):
        """
        Framework for intake testing
        """
        self.deliver_instance._INFORM_INTAKE()
        self.encoded_file = '{file_name}_{suffix}.{ext}'.format(
            file_name=self.veda_id,
            suffix=self.encode.encode_suffix,
            ext=self.encode.encode_filetype
        )
        self.assertEqual(self.deliver_instance.encoded_file, self.encoded_file)
        self.assertEqual(
            self.deliver_instance.hotstore_url,
            '/'.join((
                'https:/',
                's3.amazonaws.com',
                CONFIG_DATA['veda_deliverable_bucket'],
                self.encoded_file
            ))
        )

    @unittest.skip('Skipping this test due to unavailability of ffprobe req')
    def test_validate(self):
        """
        Simple test of validation call from deliver, not a full test of validation function
        """
        self.deliver_instance.node_work_directory = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            'test_files'
        )
        self.deliver_instance.encoded_file = 'OVTESTFILE_01.mp4'
        self.assertTrue(self.deliver_instance._VALIDATE())

    def test_determine_status(self):
        """
        Test Video Status determiner
        """
        self.deliver_instance.video_query = self.video

        self.assertEqual(self.deliver_instance._DETERMINE_STATUS(), 'Progress')
        self.url = URL.objects.create(
            encode_profile=self.encode,
            videoID=self.video,
            encode_url='Test_URL'
        )

        self.assertEqual(self.deliver_instance._DETERMINE_STATUS(), 'Complete')

    def test_validate_url(self):
        """
        Test URL Validator
        """
        self.assertFalse(self.deliver_instance._VALIDATE_URL())
        self.deliver_instance.endpoint_url = 'https://edx.org'
        self.assertTrue(self.deliver_instance._VALIDATE_URL())

    @patch('control.veda_val.VALAPICall._AUTH', PropertyMock(return_value=lambda: CONFIG_DATA))
    @patch('control.veda_val.OAuthAPIClient.request')
    @responses.activate
    def test_update_data(self, _):
        """
        Run test of VAL status / call
        """
        # VAL Patching
        responses.add(
            responses.GET,
            CONFIG_DATA['val_api_url'] + '/XXXXXXXX2014-V00TES1',
            status=200,
            json={'error': 'null', 'courses': [], 'encoded_videos': []}
        )
        responses.add(responses.PUT, CONFIG_DATA['val_api_url'] + '/XXXXXXXX2014-V00TES1', status=200)
        self.VP = VideoProto(
            client_title='Test Video',
            veda_id=self.veda_id
        )
        self.deliver_instance.video_query = self.video
        # No Update
        self.deliver_instance._UPDATE_DATA()
        self.assertEqual(self.deliver_instance.val_status, None)
        # Incomplete
        self.deliver_instance.status = 'Garbled'
        self.deliver_instance._UPDATE_DATA()
        self.assertEqual(self.deliver_instance.val_status, 'transcode_active')
        # Complete
        self.deliver_instance.status = 'Complete'
        self.deliver_instance._UPDATE_DATA()
        self.assertEqual(self.deliver_instance.val_status, 'file_complete')
