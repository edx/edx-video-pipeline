"""
Tests common utils
"""
from unittest import TestCase

from ddt import data, ddt, unpack
from django.conf import settings
from django.test import override_settings, TransactionTestCase
from mock import MagicMock, Mock

from VEDA_OS01 import utils
from VEDA_OS01.models import TranscriptCredentials
from VEDA_OS01.tests.factories import CourseFactory, DestinationFactory, EncodeFactory, VideoFactory, UrlFactory
from VEDA_OS01.utils import get_incomplete_encodes, is_video_ready

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


class EncodeUtilsTest(TransactionTestCase):
    """
    Tests for video encode utils
    """

    def setUp(self):
        # Setup test courses
        course1 = CourseFactory(review_proc=True, yt_proc=True, s3_proc=True)
        course2 = CourseFactory(review_proc=False, yt_proc=True, s3_proc=True)
        course3 = CourseFactory(review_proc=True, yt_proc=True, s3_proc=False)

        # Setup test encode profiles
        destination = DestinationFactory(destination_active=True)
        encode1 = EncodeFactory(encode_destination=destination, product_spec='desktop_mp4', profile_active=True)
        encode2 = EncodeFactory(encode_destination=destination, product_spec='review', profile_active=True)
        encode3 = EncodeFactory(encode_destination=destination, product_spec='mobile_low', profile_active=True)
        encode4 = EncodeFactory(encode_destination=destination, product_spec='audio_mp3', profile_active=True)
        encode5 = EncodeFactory(encode_destination=destination, product_spec='hls', profile_active=False)
        encode6 = EncodeFactory(encode_destination=destination, product_spec='youtube', profile_active=True)

        # Setup videos
        self.video1 = VideoFactory(inst_class=course1)
        self.video2 = VideoFactory(inst_class=course2)
        self.video3 = VideoFactory(inst_class=course3)

        # Setup urls for video1
        UrlFactory(encode_profile=encode1, videoID=self.video1)
        UrlFactory(encode_profile=encode2, videoID=self.video1)
        UrlFactory(encode_profile=encode3, videoID=self.video1)
        UrlFactory(encode_profile=encode4, videoID=self.video1)
        UrlFactory(encode_profile=encode5, videoID=self.video1)
        UrlFactory(encode_profile=encode6, videoID=self.video1)

        # Setup urls for video2
        UrlFactory(encode_profile=encode1, videoID=self.video2)
        UrlFactory(encode_profile=encode3, videoID=self.video2)
        UrlFactory(encode_profile=encode6, videoID=self.video2)

        # Setup urls for video3
        UrlFactory(encode_profile=encode6, videoID=self.video3)

    def test_get_incomplete_encodes_invalid_video(self):
        """
        Tests that `get_incomplete_encodes` returns an empty list with non existent video id.
        """
        self.assertEqual(get_incomplete_encodes(u'non-existent-id'), [])

    def test_get_incomplete_encodes(self):
        """
        Tests that `get_incomplete_encodes` works as expected.
        """
        self.assertEqual(get_incomplete_encodes(self.video1.edx_id), [])
        self.assertEqual(get_incomplete_encodes(self.video2.edx_id), ['audio_mp3'])
        self.assertEqual(get_incomplete_encodes(self.video3.edx_id), ['review'])

    def test_is_video_ready(self):
        """
        Tests that `is_video_ready` works as expected.
        """
        self.assertTrue(is_video_ready(self.video1.edx_id))
        self.assertFalse(is_video_ready(self.video2.edx_id))
        self.assertTrue(is_video_ready(self.video2.edx_id, ignore_encodes=['audio_mp3']))
        self.assertTrue(is_video_ready(self.video3.edx_id, ignore_encodes=['review', 'abc_encode']))
