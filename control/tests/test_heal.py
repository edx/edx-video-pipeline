"""
Test heal processor
"""
import datetime
import json
import os
import sys
from django.test import TestCase
from datetime import timedelta

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


class TestHeal(TestCase):

    def setUp(self):
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
