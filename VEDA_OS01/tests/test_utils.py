"""
Tests common utils
"""
from ddt import data, ddt, unpack
from mock import MagicMock, Mock
from unittest import TestCase

from VEDA_OS01 import utils


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
