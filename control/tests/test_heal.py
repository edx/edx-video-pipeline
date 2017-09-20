"""
Test heal processor
"""
import datetime
import json
import os
import sys
from django.test import TestCase
from datetime import timedelta
from ddt import data, ddt, unpack
from unittest import skip
import responses
from django.utils.timezone import utc
from mock import PropertyMock, patch

from control.veda_heal import VedaHeal
from VEDA_OS01.models import URL, Course, Destination, Encode, Video
from VEDA_OS01.utils import build_url, get_config

sys.path.append(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)
)))

CONFIG_DATA = get_config('test_config.yaml')


@ddt
class HealTests(TestCase):
    """
    Tests HEAL process
    """

    def setUp(self):
        self.heal_instance = VedaHeal()
        self.encode_list = set()

        for key, entry in CONFIG_DATA['encode_dict'].items():
            for e in entry:
                self.encode_list.add(e)

        self.video_id = '12345'
        self.course_object = Course.objects.create(
            institution='XXX',
            edx_classid='XXXXX',
            local_storedir='WestonHS/PFLC1x/3T2015'
        )

        self.video = Video.objects.create(
            inst_class=self.course_object,
            studio_id=self.video_id,
            edx_id='XXXXXXXX2014-V00TES1',
            video_trans_start=datetime.datetime.utcnow().replace(tzinfo=utc) - timedelta(
                hours=CONFIG_DATA['heal_start']
            ),
            video_trans_end=datetime.datetime.utcnow().replace(tzinfo=utc),
        )

        self.encode = Encode.objects.create(
            product_spec='mobile_low',
            encode_destination=Destination.objects.create(destination_name='destination_name')
        )
        self.encode = Encode.objects.create(
            product_spec='hls',
            encode_destination=Destination.objects.create(destination_name='destination_name')
        )

        url = URL(
            videoID=self.video,
            encode_profile=self.encode,
            encode_bitdepth='22',
            encode_url='http://veda.edx.org/encode')
        url.save()

    @patch('control.veda_heal.VALAPICall._AUTH', PropertyMock(return_value=lambda: CONFIG_DATA))
    @responses.activate
    def test_heal(self):
        val_response = {
            'courses': [{u'WestonHS/PFLC1x/3T2015': None}],
            'encoded_videos': [{
                'url': 'https://testurl.mp4',
                'file_size': 8499040,
                'bitrate': 131,
                'profile': 'mobile_low',
            }]
        }
        responses.add(
            responses.POST,
            CONFIG_DATA['val_token_url'],
            '{"access_token": "1234567890"}',
            status=200
        )
        responses.add(
            responses.GET,
            build_url(CONFIG_DATA['val_api_url'], self.video_id),
            body=json.dumps(val_response),
            content_type='application/json',
            status=200
        )
        responses.add(
            responses.PUT,
            build_url(CONFIG_DATA['val_api_url'], self.video_id),
            status=200
        )

        heal = VedaHeal()
        heal.discovery()

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
            inst_class=self.course_object
        )
        video_instance.save()

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
            inst_class=self.course_object
        )

        video_instance.save()

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
            inst_class=self.course_object
        )

        video_instance.save()

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
