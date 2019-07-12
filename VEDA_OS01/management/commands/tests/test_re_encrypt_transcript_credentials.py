"""
Tests of the re_encrypt_transcript_credentials management command.
"""
from __future__ import absolute_import
from cryptography.fernet import InvalidToken
from django.conf import settings
from django.core.management import call_command
from django.test import TestCase, override_settings
from mock import patch

from VEDA_OS01.models import TranscriptCredentials, TranscriptProvider
from VEDA_OS01.utils import invalidate_fernet_cached_properties


OLD_FERNET_KEYS_LIST = ['test-ferent-key']


class ReEncryptTranscriptCredentialsTests(TestCase):
    """
    Management command test class.
    """

    def setUp(self):
        """
        Test setup.
        """
        self.credentials_data = {
            'org': 'MAx',
            'provider': TranscriptProvider.THREE_PLAY,
            'api_key': 'test-key',
            'api_secret': 'test-secret'
        }
        TranscriptCredentials.objects.create(**self.credentials_data)

    def tearDown(self):
        """
        Test teardown.
        """
        # Invalidate here so that every new test would have FERNET KEYS from test environment.
        invalidate_fernet_cached_properties(TranscriptCredentials, ['api_key', 'api_secret'])

    def verify_access_credentials(self):
        """
        Fetches a record to check if we are able to get encrypted data.
        Accessing object that is not able to be decrypted, would throw InvalidToken error.
        """
        TranscriptCredentials.objects.get(
            org=self.credentials_data['org'], provider=self.credentials_data['provider']
        )

    @patch('VEDA_OS01.management.commands.re_encrypt_transcript_credentials.LOGGER')
    def test_reencrypt_transcript_credentials(self, mock_logger):
        """
        Test transcript credentials are re-encrypted correctly.
        """
        # Verify fernet keys.
        self.assertEqual(settings.FERNET_KEYS, OLD_FERNET_KEYS_LIST)

        # Verify we are able to access the record.
        self.verify_access_credentials()

        # Add a new key to the set
        new_keys_set = ['new-fernet-key'] + settings.FERNET_KEYS

        with override_settings(FERNET_KEYS=new_keys_set):
            self.assertEqual(settings.FERNET_KEYS, new_keys_set)
            # Run re-encryption process.
            call_command('re_encrypt_transcript_credentials')

            # Verify logging.
            mock_logger.info.assert_called_with('[Transcript credentials re-encryption] Process completed.')

            # Verify we are able to access the record.
            self.verify_access_credentials()

    @patch('VEDA_OS01.management.commands.re_encrypt_transcript_credentials.LOGGER')
    def test_reencrypt_transcript_credentials_invalid_keys(self, mock_logger):
        """
        Test transcript credentials would not be re-encrypted if an decryption key is not provided with which
        data was encypted before.
        """
        # Verify fernet keys.
        self.assertEqual(settings.FERNET_KEYS, OLD_FERNET_KEYS_LIST)

        # Verify we are able to access the record.
        self.verify_access_credentials()

        # Modify key set so that old key is not presnet in the key list. Note that now we are not providing
        # a decryption key for data to be decrypted.
        new_keys_set = ['new-fernet-key']

        with override_settings(FERNET_KEYS=new_keys_set):
            self.assertEqual(settings.FERNET_KEYS, new_keys_set)
            # Run re-encryption process.
            call_command('re_encrypt_transcript_credentials')

            # Verify logging.
            mock_logger.info.assert_called_with('[Transcript credentials re-encryption] Process started.')
            mock_logger.exception.assert_called_with(
                '[Transcript credentials re-encryption] No valid fernet key present to decrypt. Process halted.'
            )

            # Verify we are not able to access the record, we should get an error due to decryption key not present.
            with self.assertRaises(InvalidToken):
                self.verify_access_credentials()
