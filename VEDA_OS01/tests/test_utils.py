"""
Tests common utils
"""
from unittest import TestCase

from ddt import data, ddt, unpack
from django.conf import settings
from django.test import override_settings
from mock import MagicMock, Mock

from VEDA_OS01 import utils
from VEDA_OS01.models import TranscriptCredentials


OLD_FERNET_KEYS_LIST = ['test-ferent-key']


@ddt
class UtilTests(TestCase):
    """
    Common util tests.
    """
    @data(
        ('IN PROGRESS', True),
        ('FAILED', False)
    )
    @unpack
    def test_video_status_update(self, status, update_val_status):
        """
        Tests that  utils.video_status_update works as expected.
        """
        val_api_client = MagicMock()
        video = Mock(studio_id='1234', transcript_status='earlier status')
        # Make call to update_video_status.
        utils.update_video_status(val_api_client=val_api_client, video=video, status=status)
        # Assert the status and call to edx-val api method.
        self.assertEqual(val_api_client.update_video_status.called, update_val_status)
        self.assertEqual(video.transcript_status, status)

    def test_invalidate_fernet_cached_properties(self):
        """
        Tests that fernet field properties are properly invalidated.
        """
        def verify_model_field_keys(model, field_name, expected_keys_list):
            """
            Verifies cached property keys has expected keys list.
            """
            field = model._meta.get_field(field_name)
            # Verify keys are properly set and fetched.
            self.assertEqual(field.keys, expected_keys_list)

        self.assertEqual(settings.FERNET_KEYS, OLD_FERNET_KEYS_LIST)
        verify_model_field_keys(TranscriptCredentials, 'api_key', OLD_FERNET_KEYS_LIST)

        # Invalidate cached properties.
        utils.invalidate_fernet_cached_properties(TranscriptCredentials, ['api_key'])

        # Prepend a new key.
        new_keys_set = ['new-fernet-key'] + settings.FERNET_KEYS

        with override_settings(FERNET_KEYS=new_keys_set):
            self.assertEqual(settings.FERNET_KEYS, new_keys_set)
            verify_model_field_keys(TranscriptCredentials, 'api_key', new_keys_set)
