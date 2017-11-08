""" Model tests """
from cryptography.fernet import InvalidToken
from django.conf import settings
from django.test import override_settings
from django.test.testcases import TransactionTestCase

from VEDA_OS01.models import TranscriptCredentials, TranscriptProvider
from VEDA_OS01.utils import invalidate_fernet_cached_properties


class TranscriptCredentialsModelTest(TransactionTestCase):
    """
    Transcript credentials model tests
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
        # Invalidate here so that every new test would have FERNET KEYS from tests.py initially.
        invalidate_fernet_cached_properties(TranscriptCredentials, ['api_key', 'api_secret'])

    def test_decrypt(self):
        """
        Tests transcript credential fields are correctly decrypted.
        """
        # Verify that api key is correctly fetched.
        transcript_credentials = TranscriptCredentials.objects.get(
            org=self.credentials_data['org'], provider=self.credentials_data['provider']
        )
        self.assertEqual(transcript_credentials.api_key, self.credentials_data['api_key'])
        self.assertEqual(transcript_credentials.api_secret, self.credentials_data['api_secret'])

    def test_decrypt_different_key(self):
        """
        Tests decryption with one more key pre-pended. Note that we still have the old key with which value was
        encrypted so we should be able to decrypt it again.
        """
        old_keys_set = ['test-ferent-key']
        self.assertEqual(settings.FERNET_KEYS, old_keys_set)
        new_keys_set = ['new-fernet-key'] + settings.FERNET_KEYS

        # Invalidate cached properties so that we get the latest keys
        invalidate_fernet_cached_properties(TranscriptCredentials, ['api_key', 'api_secret'])

        with override_settings(FERNET_KEYS=new_keys_set):
            self.assertEqual(settings.FERNET_KEYS, new_keys_set)
            transcript_credentials = TranscriptCredentials.objects.get(
                org=self.credentials_data['org'], provider=self.credentials_data['provider']
            )
        self.assertEqual(transcript_credentials.api_key, self.credentials_data['api_key'])
        self.assertEqual(transcript_credentials.api_secret, self.credentials_data['api_secret'])

    def test_decrypt_different_key_set(self):
        """
        Tests decryption with different fernet key set. Note that now we don't have the old fernet key with which
        value was encrypted so we would not be able to decrypt it and we should get an Invalid Token.
        """
        old_keys_set = ['test-ferent-key']
        self.assertEqual(settings.FERNET_KEYS, old_keys_set)
        new_keys_set = ['new-fernet-key']

        # Invalidate cached properties so that we get the latest keys
        invalidate_fernet_cached_properties(TranscriptCredentials, ['api_key', 'api_secret'])

        with override_settings(FERNET_KEYS=new_keys_set):
            self.assertEqual(settings.FERNET_KEYS, new_keys_set)
            with self.assertRaises(InvalidToken):
                TranscriptCredentials.objects.get(
                    org=self.credentials_data['org'], provider=self.credentials_data['provider']
                )
