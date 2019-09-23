
from __future__ import absolute_import
import os
import sys
from django.test import TestCase
from ddt import data, ddt, unpack

from mock import Mock, PropertyMock, patch

import requests
import urllib3
import responses

from control.veda_val import VALAPICall
from VEDA import utils
from control.veda_file_ingest import VideoProto
from VEDA_OS01.utils import ValTranscriptStatus


urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
"""
This is an API connection test
set to pass if instance_config.yaml is missing
"""

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

CONFIG_DATA = utils.get_config('test_config.yaml')


@ddt
class TestVALAPI(TestCase):
    def setUp(self):
        self.VP = VideoProto(
            client_title='Test Title',
            veda_id='TESTID'
        )

        with patch.object(VALAPICall, '_AUTH', PropertyMock(return_value=lambda: CONFIG_DATA)):
            self.VAC = VALAPICall(
                video_proto=self.VP,
                val_status='complete'
            )

        self.auth_yaml = CONFIG_DATA

    def test_val_setup(self):
        # register val url to send api response
        responses.add(responses.POST, CONFIG_DATA['oauth2_provider_url'], '{"access_token": "1234567890"}', status=200)

        salient_variables = [
            'val_api_url',
            'oauth2_client_id',
            'oauth2_client_secret',
            'oauth2_provider_url',
        ]
        for salient_variable in salient_variables:
            self.assertTrue(len(self.VAC.auth_dict[salient_variable]) > 0)

    @responses.activate
    def test_val_connection(self):
        # register val url to send api response
        responses.add(responses.GET, CONFIG_DATA['val_api_url'], status=200)

        response = requests.get(
            self.VAC.auth_dict['val_api_url'],
            headers=self.VAC.headers,
            timeout=20
        )

        self.assertFalse(response.status_code == 404)
        self.assertFalse(response.status_code > 299)

    @data(
        {
            'encode_list': [],
            'val_status': 'file_complete',
            'expected_response': False
        },
        {
            'encode_list': [],
            'val_status': ValTranscriptStatus.TRANSCRIPT_READY,
            'expected_response': False
        },
        {
            'encode_list': [],
            'val_status': ValTranscriptStatus.TRANSCRIPTION_IN_PROGRESS,
            'expected_response': False
        },
        {
            'encode_list': ['abc.mp4'],
            'val_status': 'file_complete',
            'expected_response': True
        },
        {
            'encode_list': ['abc.mp4'],
            'val_status': ValTranscriptStatus.TRANSCRIPT_READY,
            'expected_response': True
        },
        {
            'encode_list': ['abc.mp4'],
            'val_status': ValTranscriptStatus.TRANSCRIPTION_IN_PROGRESS,
            'expected_response': True
        },
    )
    @unpack
    def test_val_should_update_status(self, encode_list, val_status, expected_response):
        """
        Verify that `should_update_status` works as expected.
        """
        response = self.VAC.should_update_status(encode_list, val_status)
        self.assertEqual(response, expected_response)
