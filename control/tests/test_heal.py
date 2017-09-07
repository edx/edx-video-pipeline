"""
Tests HEAL process
"""
import datetime
import os
from datetime import timedelta
from unittest import TestCase

import yaml
from ddt import data, ddt, unpack
from django.utils.timezone import utc

from veda_heal import VedaHeal
from VEDA_OS01.models import Course, Video


@ddt
class HealTests(TestCase):
    """
    Tests HEAL process
    """

    def setUp(self):
        self.heal_instance = VedaHeal()
        self.auth_yaml = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            'instance_config.yaml'
        )
        self.encode_list = set()
        with open(self.auth_yaml, 'r') as stream:
            for key, entry in yaml.load(stream)['encode_dict'].items():
                for e in entry:
                    self.encode_list.add(e)

    @data(
        {
            'edx_id': '1',
            'video_trans_status': 'Corrupt File',
            'video_trans_start': datetime.datetime.utcnow().replace(tzinfo=utc),
            'video_active': True,
        },
        {
            'edx_id': '1',
            'video_trans_status': 'Review Reject',
            'video_trans_start': datetime.datetime.utcnow().replace(tzinfo=utc),
            'video_active': True,
        },
        {
            'edx_id': '1',
            'video_trans_status': 'Review Hold',
            'video_trans_start': datetime.datetime.utcnow().replace(tzinfo=utc),
            'video_active': True,
        },
        {
            'edx_id': '1',
            'video_trans_status': 'Complete',
            'video_trans_start': datetime.datetime.utcnow().replace(tzinfo=utc),
            'video_active': False,
        },
        {
            'edx_id': '2',
            'video_trans_status': 'Ingest',
            'video_trans_start': datetime.datetime.utcnow().replace(tzinfo=utc),
            'video_active': True,
        },
        {
            'edx_id': '1',
            'video_trans_status': 'Corrupt File',
            'video_trans_start': datetime.datetime.utcnow().replace(tzinfo=utc),
            'video_active': True,
        },
    )
    @unpack
    def test_determine_fault(self, edx_id, video_trans_status, video_trans_start, video_active):
        """
        Tests that determine_fault works in various video states.
        """
        video_instance = Video(
            edx_id=edx_id,
            video_trans_status=video_trans_status,
            video_trans_start=video_trans_start,
            video_active=video_active,
            inst_class=Course()
        )
        encode_list = self.heal_instance.determine_fault(video_instance)

        if video_instance.edx_id == '1':
            self.assertEqual(encode_list, [])
        elif video_instance.edx_id == '2':
            for e in encode_list:
                self.assertTrue(e in self.encode_list)

    @data(
        {
            'uncompleted_encodes': [],
            'expected_encodes': ['test_obj'],
            'video_object': {
                'edx_id': '1',
                'video_trans_status': 'Complete',
                'video_trans_start': datetime.datetime.utcnow().replace(tzinfo=utc),
                'video_active': True,
            }
        },
        {
            'uncompleted_encodes': ['test_obj'],
            'expected_encodes': ['test_obj'],
            'video_object': {
                'edx_id': '2',
                'video_trans_status': 'Ingest',
                'video_trans_start': datetime.datetime.utcnow().replace(tzinfo=utc),
                'video_active': True,
            }
        }
    )
    @unpack
    def test_differentiate_encodes(self, uncompleted_encodes, expected_encodes, video_object):
        """
        Tests that differentiate_encodes list comparison works as expected. This doesn't test video states,
        just the list comparison function.
        """
        video_instance = Video(
            edx_id=video_object['edx_id'],
            video_trans_status=video_object['video_trans_status'],
            video_trans_start=video_object['video_trans_start'],
            video_active=video_object['video_active'],
            inst_class=Course()
        )

        encode_list = self.heal_instance.differentiate_encodes(
            uncompleted_encodes,
            expected_encodes,
            video_instance
        )

        if video_instance.edx_id == '1':
            self.assertEqual(encode_list, [])
        elif video_instance.edx_id == '2':
            self.assertEqual(encode_list, ['test_obj'])

    @data(
        {
            'uncompleted_encodes': ['test_encode', 'test_encode'],
            'expected_encodes': ['test_encode', 'test_encode'],
            'video_object': {
                'edx_id': '1',
                'video_trans_status': 'Complete',
                'video_trans_start': datetime.datetime.utcnow().replace(tzinfo=utc),
                'video_active': True,
            }
        },
        {
            'uncompleted_encodes': ['test_encode', 'test_encode', 'hls'],
            'expected_encodes': ['test_encode', 'test_encode', 'hls'],
            'video_object': {
                'edx_id': '2',
                'video_trans_status': 'Complete',
                'video_trans_start': datetime.datetime.utcnow().replace(tzinfo=utc),
                'video_active': True,
            }
        },
        {
            'uncompleted_encodes': ['test_encode', 'test_encode', 'hls'],
            'expected_encodes': ['test_encode', 'test_encode', 'hls'],
            'video_object': {
                'edx_id': '3',
                'video_trans_status': 'Ingest',
                'video_trans_start': datetime.datetime.utcnow().replace(tzinfo=utc) - timedelta(days=10),
                'video_active': True,
            }
        }
    )
    @unpack
    def test_determine_longterm_corrupt(self, uncompleted_encodes, expected_encodes, video_object):
        video_instance = Video(
            edx_id=video_object['edx_id'],
            video_trans_status=video_object['video_trans_status'],
            video_trans_start=video_object['video_trans_start'],
            video_active=video_object['video_active'],
            inst_class=Course()
        )

        longterm_corrupt = self.heal_instance.determine_longterm_corrupt(
            uncompleted_encodes,
            expected_encodes,
            video_instance
        )

        if video_instance.edx_id == '1':
            self.assertEqual(longterm_corrupt, False)
        elif video_instance.edx_id == '2':
            self.assertEqual(longterm_corrupt, False)
        elif video_instance.edx_id == '3':
            self.assertEqual(longterm_corrupt, True)

if __name__ == '__main__':
    unittest.main()
