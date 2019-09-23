"""
Test heal processor
"""
from __future__ import absolute_import
import datetime
import json
import os
import sys
from django.test import TestCase
from datetime import timedelta
from ddt import data, ddt, unpack
import responses
from django.utils.timezone import utc
from mock import PropertyMock, patch

from control_env import HEAL_START
from control.veda_heal import VedaHeal
from VEDA_OS01.models import URL, Course, Destination, Encode, Video, TranscriptStatus
from VEDA_OS01.utils import ValTranscriptStatus
from VEDA.utils import build_url, get_config

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
                hours=HEAL_START
            ),
            video_trans_end=datetime.datetime.utcnow().replace(tzinfo=utc),
        )

        self.encode = Encode.objects.create(
            product_spec='mobile_low',
            encode_destination=Destination.objects.create(destination_name='destination_name')
        )
        self.hls_encode = Encode.objects.create(
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
    @patch('control.veda_val.OAuthAPIClient')
    @responses.activate
    def test_heal(self, mock_client_init):
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
            'video_trans_status': 'Review Reject',
            'video_trans_start': datetime.datetime.utcnow().replace(tzinfo=utc),
            'video_active': True,
            'expected_encodes': []
        },
        {
            'video_trans_status': 'Review Hold',
            'video_trans_start': datetime.datetime.utcnow().replace(tzinfo=utc),
            'video_active': True,
            'expected_encodes': []
        },
    )
    @unpack
    def test_determine_fault(self, video_trans_status, video_trans_start, video_active, expected_encodes):
        """
        Tests that determine_fault works in various video states.
        """
        video_instance = Video(
            edx_id='test_id',
            video_trans_status=video_trans_status,
            video_trans_start=video_trans_start,
            video_active=video_active,
            inst_class=self.course_object
        )
        video_instance.save()

        encodes = self.heal_instance.determine_fault(video_instance)
        self.assertEqual(encodes, expected_encodes)

    @data(
        {
            'video_trans_status': 'Corrupt File',
            'video_trans_start': datetime.datetime.utcnow().replace(tzinfo=utc),
            'video_active': True,
            'expected_encodes': []
        },
        {
            'video_trans_status': 'Review Reject',
            'video_trans_start': datetime.datetime.utcnow().replace(tzinfo=utc),
            'video_active': True,
            'expected_encodes': []

        },
        {
            'video_trans_status': 'Review Hold',
            'video_trans_start': datetime.datetime.utcnow().replace(tzinfo=utc),
            'video_active': True,
            'expected_encodes': []

        },
        {
            'video_trans_status': 'Corrupt File',
            'video_trans_start': datetime.datetime.utcnow().replace(tzinfo=utc),
            'video_active': True,
            'expected_encodes': []

        },
    )
    @unpack
    def test_determine_fault_freeze_bug(
            self, video_trans_status, video_trans_start, video_active, expected_encodes
    ):
        video_instance = Video(
            edx_id='test_id',
            video_trans_status=video_trans_status,
            video_trans_start=video_trans_start,
            video_active=video_active,
            inst_class=self.course_object
        )
        video_instance.save()

        heal_instance_two = VedaHeal(freezing_bug=True)
        encode_list = heal_instance_two.determine_fault(video_instance)
        self.assertEqual(encode_list, expected_encodes)


    @data(
        {
            'uncompleted_encodes': [],
            'expected_encodes': ['test_obj'],
            'video_props': {
                'edx_id': '1',
                'video_trans_status': 'Complete',
                'video_trans_start': datetime.datetime.utcnow().replace(tzinfo=utc),
                'video_active': True,
            },
            'result': []
        },
        {
            'uncompleted_encodes': ['test_obj'],
            'expected_encodes': ['test_obj'],
            'video_props': {
                'edx_id': '2',
                'video_trans_status': 'Ingest',
                'video_trans_start': datetime.datetime.utcnow().replace(tzinfo=utc),
                'video_active': True,
            },
            'result': ['test_obj']
        }
    )
    @unpack
    def test_differentiate_encodes(self, uncompleted_encodes, expected_encodes, video_props, result):
        """
        Tests that differentiate_encodes list comparison works as expected. This doesn't test video states,
        just the list comparison function.
        """
        video_instance = Video.objects.create(inst_class=self.course_object, **video_props)
        encode_list = self.heal_instance.differentiate_encodes(
            uncompleted_encodes,
            expected_encodes,
            video_instance
        )
        self.assertEqual(encode_list, result)

    @data(
        {
            'uncompleted_encodes': [],
            'expected_encodes': ['test_obj'],
            'video_props': {
                'edx_id': '1',
                'video_trans_status': 'Complete',
                'video_trans_start': datetime.datetime.utcnow().replace(tzinfo=utc),
                'video_active': True,
                'transcript_status': TranscriptStatus.PENDING
            },
            'expected_val_status': 'file_complete'
        },
        {
            'uncompleted_encodes': [],
            'expected_encodes': ['test_obj'],
            'video_props': {
                'edx_id': '1',
                'video_trans_status': 'Complete',
                'video_trans_start': datetime.datetime.utcnow().replace(tzinfo=utc),
                'video_active': True,
                'transcript_status': TranscriptStatus.IN_PROGRESS
            },
            'expected_val_status': ValTranscriptStatus.TRANSCRIPTION_IN_PROGRESS
        },
        {
            'uncompleted_encodes': [],
            'expected_encodes': ['test_obj'],
            'video_props': {
                'edx_id': '1',
                'video_trans_status': 'Complete',
                'video_trans_start': datetime.datetime.utcnow().replace(tzinfo=utc),
                'video_active': True,
                'transcript_status': TranscriptStatus.READY
            },
            'expected_val_status': ValTranscriptStatus.TRANSCRIPT_READY
        },
        {
            'uncompleted_encodes': ['test_obj'],
            'expected_encodes': ['test_obj'],
            'video_props': {
                'edx_id': '2',
                'video_trans_status': 'Ingest',
                'video_trans_start': datetime.datetime.utcnow().replace(tzinfo=utc),
                'video_active': True,
                'transcript_status': TranscriptStatus.READY
            },
            'expected_val_status': 'transcode_queue'
        }
    )
    @unpack
    def test_differentiate_encodes_val_status(self, uncompleted_encodes,
                                              expected_encodes, video_props, expected_val_status):
        """
        Tests that the val status changes as expected based on encode list.
        """
        video_instance = Video.objects.create(inst_class=self.course_object, **video_props)
        self.heal_instance.differentiate_encodes(
            uncompleted_encodes,
            expected_encodes,
            video_instance
        )
        self.assertEqual(self.heal_instance.val_status, expected_val_status)

    @data(
        {
            'uncompleted_encodes': ['test_encode', 'test_encode'],
            'expected_encodes': ['test_encode', 'test_encode'],
            'expected_long_corrupt': False,
            'video_object': {
                'video_trans_status': 'Complete',
                'video_trans_start': datetime.datetime.utcnow().replace(tzinfo=utc),
                'video_active': True,
            }
        },
        {
            'uncompleted_encodes': ['test_encode', 'test_encode', 'hls'],
            'expected_encodes': ['test_encode', 'test_encode', 'hls'],
            'expected_long_corrupt': False,
            'video_object': {
                'video_trans_status': 'Complete',
                'video_trans_start': datetime.datetime.utcnow().replace(tzinfo=utc),
                'video_active': True,
            }
        },
        {
            'uncompleted_encodes': ['test_encode', 'test_encode', 'hls'],
            'expected_encodes': ['test_encode', 'test_encode', 'hls'],
            'expected_long_corrupt': True,
            'video_object': {
                'video_trans_status': 'Ingest',
                'video_trans_start': datetime.datetime.utcnow().replace(tzinfo=utc) - timedelta(days=10),
                'video_active': True,
            }
        }
    )
    @unpack
    def test_determine_longterm_corrupt(self, uncompleted_encodes, expected_encodes, video_object, expected_long_corrupt):
        video_instance = Video(
            edx_id='test_id',
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

        self.assertEqual(longterm_corrupt, expected_long_corrupt)
