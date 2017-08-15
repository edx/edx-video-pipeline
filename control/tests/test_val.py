
import ast
import os
import sys
from django.test import TestCase

from mock import PropertyMock, patch

import requests
import responses

from control.veda_val import VALAPICall
from veda_file_ingest import VideoProto
from VEDA_OS01 import utils


requests.packages.urllib3.disable_warnings()
"""
This is an API connection test
set to pass if instance_config.yaml is missing
"""

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

CONFIG_DATA = utils.get_config('test_config.yaml')


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

        self.auth_yaml = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'instance_config.yaml'
        )

    def test_val_setup(self):
        if not os.path.exists(self.auth_yaml):
            self.assertTrue(self.VAC.auth_dict is None)
            return None

        # register val url to send api response
        responses.add(responses.POST, CONFIG_DATA['val_token_url'], '{"access_token": "1234567890"}', status=200)

        salient_variables = [
            'val_api_url',
            'val_client_id',
            'val_password',
            'val_secret_key',
            'val_username',
            'val_token_url',
        ]
        for salient_variable in salient_variables:
            self.assertTrue(len(self.VAC.auth_dict[salient_variable]) > 0)

    @responses.activate
    def test_val_connection(self):
        if not os.path.exists(self.auth_yaml):
            self.assertTrue(self.VAC.auth_dict is None)
            return None

        # register val url to send api response
        responses.add(responses.POST, CONFIG_DATA['val_token_url'], '{"access_token": "1234567890"}', status=200)
        responses.add(responses.GET, CONFIG_DATA['val_api_url'], status=200)

        self.VAC.val_tokengen()
        self.assertFalse(self.VAC.val_token is None)

        response = requests.get(
            self.VAC.auth_dict['val_api_url'],
            headers=self.VAC.headers,
            timeout=20
        )

        self.assertFalse(response.status_code == 404)
        self.assertFalse(response.status_code > 299)
