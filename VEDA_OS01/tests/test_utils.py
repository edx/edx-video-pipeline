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
        {
            'urls': ('http://api.cielo24/', '/add/job'),
            'params': {},
            'expected_url': 'http://api.cielo24/add/job'
        },
        {
            'urls': ('http://api.cielo24', '/add/job'),
            'params': {'a': 1, 'b': 2},
            'expected_url': 'http://api.cielo24/add/job?a=1&b=2'
        },
        {
            'urls': ('http://api.cielo24/', 'add/job'),
            'params': {'c': 3, 'd': 4},
            'expected_url': 'http://api.cielo24/add/job?c=3&d=4'
        },
        {
            'urls': ('http://api.cielo24','add/job'),
            'params': {'p': 100},
            'expected_url': 'http://api.cielo24/add/job?p=100'
        },
        {
            'urls': ('http://api.cielo24', 'add/job', 'media'),
            'params': {'p': 100},
            'expected_url': 'http://api.cielo24/add/job/media?p=100'
        }
    )
    @unpack
    def test_build_url(self, urls, params, expected_url):
        """
        Tests that utils.build_url works as expected.
        """
        url = utils.build_url(
            *urls,
            **params
        )
        self.assertEqual(
            url,
            expected_url
        )

    @data(
        {
            'course_id': 'course-v1:MITx+4.605x+3T2017',
            'expected_org': 'MITx'
        },
        {
            'course_id': 'WestonHS/PFLC1x/3T2015',
            'expected_org': 'WestonHS'
        },
        {
            'course_id': '',
            'expected_org': None
        },

    )
    @unpack
    def test_extract_course_org(self, course_id, expected_org):
        """
        Tests that utils.extract_course_org works as expected.
        """
        org = utils.extract_course_org(course_id)
        self.assertEqual(
            org,
            expected_org
        )

    def test_get_config(self):
        """
        Tests that utils.get_config works as expected.
        """
        config = utils.get_config()
        self.assertNotEqual(config, {})

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
