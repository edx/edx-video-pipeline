"""
Tests common utils
"""
from ddt import data, ddt, unpack
from mock import Mock
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

    def test_video_status_update(self):
        """
        Tests that  utils.video_status_update works as expected.
        """
        def update_video_status(*args):
            expected_args = ('1234', 'afterwards status')
            self.assertEqual(args, expected_args)

        video = Mock(studio_id='1234', video_trans_status='earlier status')
        val_api_client = Mock(update_video_status=update_video_status)

        # Make call to update_video_status.
        utils.update_video_status(
            val_api_client=val_api_client,
            video=video,
            status='afterwards status'
        )

        # assert the status
        self.assertEqual(video.video_trans_status, 'afterwards status')
