
import ast
import os
import sys
import unittest

import requests
import yaml

from veda_file_ingest import VideoProto
from veda_val import VALAPICall

requests.packages.urllib3.disable_warnings()
"""
This is an API connection test
set to pass if instance_config.yaml is missing

"""

sys.path.append(os.path.dirname(os.path.dirname(__file__)))


class TestVALAPI(unittest.TestCase):

    def setUp(self):
        self.VP = VideoProto(
            client_title='Test Title',
            veda_id='TESTID'
        )

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

        salient_variables = [
            'val_api_url',
            'val_client_id',
            'val_password',
            'val_secret_key',
            'val_username',
            'val_token_url',
        ]
        for s in salient_variables:
            self.assertTrue(len(self.VAC.auth_dict[s]) > 0)

    def test_val_connection(self):
        if not os.path.exists(self.auth_yaml):
            self.assertTrue(self.VAC.auth_dict is None)
            return None

        self.VAC.val_tokengen()
        self.assertFalse(self.VAC.val_token is None)

        s = requests.get(
            self.VAC.auth_dict['val_api_url'],
            headers=self.VAC.headers,
            timeout=20
        )

        self.assertFalse(s.status_code == 404)
        self.assertFalse(s.status_code > 299)


def main():
    unittest.main()


if __name__ == '__main__':
    sys.exit(main())
