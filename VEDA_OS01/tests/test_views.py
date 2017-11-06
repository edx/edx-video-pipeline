""" Views tests """
import json

import responses
from ddt import data, ddt, unpack
from django.contrib.auth.models import User
from django.core.urlresolvers import reverse
from django.db.utils import DatabaseError
from mock import patch
from rest_framework import status
from rest_framework.test import APITestCase

from VEDA_OS01.enums import TranscriptionProviderErrorType
from VEDA_OS01.models import TranscriptCredentials, TranscriptProvider
from VEDA_OS01.views import CIELO24_LOGIN_URL


@ddt
class TranscriptCredentialsTest(APITestCase):
    """
    Transcript credentials tests
    """
    def setUp(self):
        """
        Tests setup.
        """
        super(TranscriptCredentialsTest, self).setUp()
        self.url = reverse('transcript_credentials')
        self.user = User.objects.create_user('test_user', 'test@user.com', 'test')
        self.client.login(username=self.user.username, password='test')

    def test_transcript_credentials_get_not_allowed(self):
        """
        Tests that GET method is not allowed.
        """
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_transcript_credentials_unauthorized(self):
        """
        Tests that if user is not logged in we get Unauthorized response.
        """
        # Logout client if previously logged in.
        self.client.logout()

        # Try to send post without being authorized / logged in.
        response = self.client.post(
            self.url,
            data=json.dumps({'org': 'test'}),
            content_type='application/json'
        )

        response_status_code = response.status_code
        self.assertEqual(response_status_code, status.HTTP_401_UNAUTHORIZED)

    @data(
        {},
        {
            'provider': 'unsupported-provider'
        },
        {
            'org': 'test',
            'api_key': 'test-api-key'
        }
    )
    def test_transcript_credentials_invalid_provider(self, post_data):
        """
        Test that post crednetials gives proper error in case of invalid provider.
        """
        # Verify that transcript credentials are not present for this org and provider.
        provider = post_data.get('provider')
        response = self.client.post(
            self.url,
            data=json.dumps(post_data),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        response = json.loads(response.content)
        self.assertDictEqual(response, {
            'message': 'Invalid provider {provider}.'.format(provider=provider),
            'error_type': TranscriptionProviderErrorType.INVALID_PROVIDER
        })

    @data(
        (
            {
                'provider': TranscriptProvider.CIELO24
            },
            'org and api_key and username'
        ),
        (
            {
                'provider': TranscriptProvider.THREE_PLAY
            },
            'org and api_key and api_secret_key'
        ),
        (
            {
                'provider': TranscriptProvider.CIELO24,
                'org': 'test-org'
            },
            'api_key and username'
        ),
        (
            {
                'provider': TranscriptProvider.CIELO24,
                'org': 'test-org',
                'api_key': 'test-api-key'
            },
            'username'
        ),
        (
            {
                'org': 'test',
                'provider': TranscriptProvider.THREE_PLAY,
                'api_key': 'test-api-key'
            },
            'api_secret_key'
        )
    )
    @unpack
    def test_transcript_credentials_error(self, post_data, missing_keys):
        """
        Test that post credentials gives proper error in case of invalid input.
        """
        provider = post_data.get('provider')
        error_message = '{missing} must be specified for {provider}.'.format(
            provider=provider,
            missing=missing_keys
        )
        response = self.client.post(
            self.url,
            data=json.dumps(post_data),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        response = json.loads(response.content)
        self.assertDictEqual(response, {
            'message': error_message,
            'error_type': TranscriptionProviderErrorType.MISSING_REQUIRED_ATTRIBUTES
        })

    @data(
        {
            'org': 'test',
            'provider': TranscriptProvider.CIELO24,
            'api_key': 'test-api-key',
            'username': 'test-cielo-user'
        },
        {
            'org': 'test',
            'provider': TranscriptProvider.THREE_PLAY,
            'api_key': 'test-api-key',
            'api_secret_key': 'test-secret-key'
        }
    )
    @responses.activate
    def test_transcript_credentials_success(self, post_data):
        """
        Test that post credentials works as expected.
        """
        # Mock get_cielo_token_mock to return token
        responses.add(
            responses.GET,
            CIELO24_LOGIN_URL,
            body='{"ApiToken": "cielo-api-token"}',
            status=status.HTTP_200_OK
        )

        # Verify that transcript credentials are not present for this org and provider.
        transcript_credentials = TranscriptCredentials.objects.filter(
            org=post_data.get('org'),
            provider=post_data.get('provider')
        )
        self.assertFalse(transcript_credentials.exists())

        response = self.client.post(self.url, data=json.dumps(post_data), content_type='application/json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        transcript_credentials = TranscriptCredentials.objects.filter(
            org=post_data.get('org'),
            provider=post_data.get('provider')
        )
        self.assertTrue(transcript_credentials.exists())

    @patch('VEDA_OS01.views.LOGGER')
    @responses.activate
    def test_cielo24_error(self, mock_logger):
        """
        Test that when invalid cielo credentials are supplied, we get correct response.
        """
        # Mock get_cielo_token_response.
        error_message = 'Invalid credentials supplied.'
        responses.add(
            responses.GET,
            CIELO24_LOGIN_URL,
            body=json.dumps({'error': error_message}),
            status=status.HTTP_400_BAD_REQUEST
        )

        post_data = {
            'org': 'test',
            'provider': TranscriptProvider.CIELO24,
            'api_key': 'test-api-key',
            'username': 'test-cielo-user',
            'api_secret_key': ''
        }
        response = self.client.post(
            self.url,
            data=json.dumps(post_data),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        response = json.loads(response.content)
        self.assertDictEqual(response, {
            'message': error_message,
            'error_type': TranscriptionProviderErrorType.INVALID_CREDENTIALS
        })
        mock_logger.warning.assert_called_with(
            '[Transcript Credentials] Unable to get api token --  response %s --  status %s.',
            json.dumps({'error': error_message}),
            status.HTTP_400_BAD_REQUEST
        )


class HeartbeatTests(APITestCase):
    """
    Tests for hearbeat endpoint.
    """
    def test_heartbeat(self):
        """
        Test that heartbeat endpoint gives expected response upon success.
        """
        response = self.client.get(reverse('heartbeat'))
        assert response.status_code == 200
        assert json.loads(response.content) == {'OK': True}

    @patch('django.db.backends.utils.CursorWrapper')
    def test_heartbeat_failure_db(self, mocked_cursor_wrapper):
        """
        Test that heartbeat endpoint gives expected response when there is an error.
        """
        mocked_cursor_wrapper.side_effect = DatabaseError
        response = self.client.get(reverse('heartbeat'))
        assert response.status_code == 500
        assert json.loads(response.content) == {'OK': False}
