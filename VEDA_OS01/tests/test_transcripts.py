# -*- encoding: utf-8 -*-
"""
Transcript tests
"""
import json

import responses
from boto.s3.connection import S3Connection
from boto.s3.key import Key
from ddt import data, ddt, unpack
from django.core.urlresolvers import reverse
from mock import Mock, PropertyMock, patch
from moto import mock_s3_deprecated
from rest_framework import status
from rest_framework.test import APITestCase

from VEDA_OS01 import transcripts, utils
from VEDA_OS01.models import (Course, TranscriptPreferences,
                              TranscriptProcessMetadata, TranscriptProvider,
                              TranscriptStatus, Video)

CONFIG_DATA = utils.get_config('test_config.yaml')

VIDEO_DATA = {
    'studio_id': '12345'
}

TRANSCRIPT_PROCESS_METADATA = {
    'process_id': 100,
    'lang_code': 'en',
    'provider': TranscriptProvider.CIELO24,
    'status': TranscriptStatus.IN_PROGRESS
}

TRANSCRIPT_PREFERENCES = {
    'org': 'MAx',
    'provider': TranscriptProvider.CIELO24,
    'api_key': 'i_am_key',
    'api_secret': 'i_am_secret',
}

REQUEST_PARAMS = {'job_id': 100, 'lang_code': 'en', 'org': 'MAx', 'video_id': '111'}

TRANSCRIPT_SRT_DATA = """
1
00:00:07,180 --> 00:00:08,460
This is subtitle line 1.

2
00:00:08,460 --> 00:00:10,510
This is subtitle line 2.

3
00:00:10,510 --> 00:00:13,560
This is subtitle line 3.

4
00:00:13,560 --> 00:00:14,360
This is subtitle line 4.

5
00:00:14,370 --> 00:00:16,530
This is subtitle line 5.

6
00:00:16,500 --> 00:00:18,600
可以用“我不太懂艺术 但我知道我喜欢什么”做比喻.
"""

TRANSCRIPT_SJSON_DATA = {
    u'start': [7180, 8460, 10510, 13560, 14370, 16500],
    u'end': [8460, 10510, 13560, 14360, 16530, 18600],
    u'text': [
        u'This is subtitle line 1.',
        u'This is subtitle line 2.',
        u'This is subtitle line 3.',
        u'This is subtitle line 4.',
        u'This is subtitle line 5.',
        u'可以用“我不太懂艺术 但我知道我喜欢什么”做比喻.'
    ]
}


@ddt
@patch.dict('VEDA_OS01.transcripts.CONFIG', CONFIG_DATA)
@patch('VEDA_OS01.utils.get_config', Mock(return_value=CONFIG_DATA))
class Cielo24TranscriptTests(APITestCase):
    """
    Cielo24 Transcript Tests
    """
    def setUp(self):
        """
        Tests setup.
        """
        super(Cielo24TranscriptTests, self).setUp()
        self.url = reverse('cielo24_transcript_completed', args=[CONFIG_DATA['transcript_provider_request_token']])
        self.uuid_hex = '01234567890123456789'
        self.course = Course.objects.create(
            course_name='Intro to VEDA',
            institution='MAx',
            edx_classid='123'
        )
        self.video = Video.objects.create(
            inst_class=self.course,
            **VIDEO_DATA
        )

        self.transcript_prefs = TranscriptPreferences.objects.create(
            **TRANSCRIPT_PREFERENCES
        )

        metadata = dict(TRANSCRIPT_PROCESS_METADATA)
        metadata['video'] = self.video
        self.transcript_process_metadata = TranscriptProcessMetadata.objects.create(**metadata)

        self.transcript_create_data = {
            'file_format': transcripts.TRANSCRIPT_SJSON,
            'video_id': self.video.studio_id,
            'name': '{directory}{uuid}.sjson'.format(
                directory=CONFIG_DATA['aws_video_transcripts_prefix'], uuid=self.uuid_hex
            ),
            'language_code': 'en',
            'provider': TranscriptProvider.CIELO24
        }

        self.video_transcript_ready_status_data = {
            'status': transcripts.VideoStatus.TRANSCRIPTION_READY,
            'edx_video_id': self.video.studio_id
        }

        uuid_patcher = patch.object(
            transcripts.uuid.UUID,
            'hex',
            new_callable=PropertyMock(return_value=self.uuid_hex)
        )
        uuid_patcher.start()
        self.addCleanup(uuid_patcher.stop)

        REQUEST_PARAMS['video_id'] = self.video.studio_id

    @data(
        {'url': 'cielo24/transcript_completed', 'status_code': 404},
        {'url': None, 'status_code': 200},
    )
    @unpack
    def test_provider(self, url, status_code):
        """
        Verify that only valid provider requests are allowed .
        """
        response = self.client.get(
            url or self.url,
            {'job_id': 3, 'lang_code': 'ar', 'org': 'edx', 'video_id': 12345}
        )
        self.assertEqual(response.status_code, status_code)

    @data(
        {'params': {}},
        {'params': {'job_id': 1}},
        {'params': {'job_id': 2, 'lang_code': 'en'}},
        {'params': {'job_id': 3, 'lang_code': 'ar', 'org': 'edx'}}
    )
    @unpack
    def test_missing_required_params(self, params):
        """
        Verify that 400 response is recevied if any required param is missing.
        """
        response = self.client.get(self.url, params)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_transcript_callback_get_request(self):
        """
        Verify that transcript callback get request is working as expected.
        """
        def signal_handler(**kwargs):
            """
            signal handler for testing.
            """
            for key, value in REQUEST_PARAMS.items():
                self.assertEqual(kwargs[key], value)

        transcripts.CIELO24_TRANSCRIPT_COMPLETED.connect(signal_handler)
        response = self.client.get(self.url, REQUEST_PARAMS)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    @patch('VEDA_OS01.transcripts.VALAPICall._AUTH', PropertyMock(return_value=lambda: CONFIG_DATA))
    @responses.activate
    @mock_s3_deprecated
    def test_cielo24_callback(self):
        """
        Verify that `cielo24_transcript_callback` method works as expected.
        """
        # register urls to be listen by responses
        responses.add(
            responses.GET,
            transcripts.CIELO24_GET_CAPTION_URL,
            body=TRANSCRIPT_SRT_DATA,
            adding_headers={'Content-Type': 'text/plain; charset=utf-8'},
            content_type='text/plain',
            status=200
        )
        responses.add(responses.POST, CONFIG_DATA['val_token_url'], '{"access_token": "1234567890"}', status=200)
        responses.add(responses.POST, CONFIG_DATA['val_transcript_create_url'], status=200)
        responses.add(responses.PATCH, CONFIG_DATA['val_video_transcript_status_url'], status=200)

        # create s3 bucket -- all this is happening in moto's virtual environment
        conn = S3Connection()
        conn.create_bucket(CONFIG_DATA['aws_video_transcripts_bucket'])

        transcripts.cielo24_transcript_callback(None, **REQUEST_PARAMS)

        # Total of 4 HTTP requests are made as registered above
        self.assertEqual(len(responses.calls), 4)

        # verify requests
        self.assertTrue(
            responses.calls[0].request.url,
            'http://api.cielo24.com/job/get_caption?api_token=i_am_key&job_id=%28100%2C%29&caption_format=SRT&v=1'
        )

        self.assertEqual(responses.calls[2].request.url, CONFIG_DATA['val_transcript_create_url'])
        transcript_create_request_data = json.loads(responses.calls[2].request.body)
        self.assertEqual(transcript_create_request_data, self.transcript_create_data)

        self.assertEqual(responses.calls[3].request.url, CONFIG_DATA['val_video_transcript_status_url'])
        self.assertEqual(json.loads(responses.calls[3].request.body), self.video_transcript_ready_status_data)

        # verify sjson data uploaded to s3
        bucket = conn.get_bucket(CONFIG_DATA['aws_video_transcripts_bucket'])
        key = Key(bucket)
        key.key = transcript_create_request_data['name']
        sjson = json.loads(key.get_contents_as_string())
        self.assertEqual(sjson, TRANSCRIPT_SJSON_DATA)

    @patch('VEDA_OS01.transcripts.LOGGER')
    @responses.activate
    def test_fetch_exception_log(self, mock_logger):
        """
        Verify that correct exception log created for `fetch_srt_data` function error.
        """
        responses.add(responses.GET, transcripts.CIELO24_GET_CAPTION_URL, status=400)

        transcripts.cielo24_transcript_callback(None, **REQUEST_PARAMS)
        mock_logger.exception.assert_called_with(
            '[CIELO24 TRANSCRIPTS] Fetch request failed for video=%s -- lang=%s -- job_id=%s',
            REQUEST_PARAMS['video_id'],
            REQUEST_PARAMS['lang_code'],
            REQUEST_PARAMS['job_id']
        )

    @patch('VEDA_OS01.transcripts.LOGGER')
    @responses.activate
    def test_conversion_exception_log(self, mock_logger):
        """
        Verify that correct exception log created for `convert_srt_to_sjson` function error.
        """
        conversion_exception_message = 'conversion failed'
        responses.add(responses.GET, transcripts.CIELO24_GET_CAPTION_URL, body='aaa', status=200)
        with patch('VEDA_OS01.transcripts.convert_srt_to_sjson') as mock_convert_srt_to_sjson:
            mock_convert_srt_to_sjson.side_effect = transcripts.TranscriptConversionError(conversion_exception_message)
            with self.assertRaises(transcripts.TranscriptConversionError) as conversion_exception:
                transcripts.cielo24_transcript_callback(None, **REQUEST_PARAMS)
                mock_logger.exception.assert_called_with(
                    '[CIELO24 TRANSCRIPTS] Request failed for video=%s -- lang=%s -- job_id=%s -- message=%s',
                    REQUEST_PARAMS['video_id'],
                    REQUEST_PARAMS['lang_code'],
                    REQUEST_PARAMS['job_id']
                )

            self.assertEqual(
                conversion_exception.exception.message,
                conversion_exception_message
            )

    @patch('VEDA_OS01.transcripts.LOGGER')
    @responses.activate
    def test_s3_exception_log(self, mock_logger):
        """
        Verify that correct exception log created for `convert_srt_to_sjson` function error.
        """
        s3_message = 'upload failed'
        responses.add(responses.GET, transcripts.CIELO24_GET_CAPTION_URL, body='aaa', status=200)
        with patch('VEDA_OS01.transcripts.convert_srt_to_sjson') as mock_convert_srt_to_sjson:
            with patch('VEDA_OS01.transcripts.upload_sjson_to_s3') as mock_upload_sjson_to_s3:
                mock_convert_srt_to_sjson.return_value = {'a': 1}
                mock_upload_sjson_to_s3.side_effect = transcripts.TranscriptConversionError(s3_message)
                with self.assertRaises(transcripts.TranscriptConversionError) as s3_exception:
                    transcripts.cielo24_transcript_callback(None, **REQUEST_PARAMS)
                    mock_logger.exception.assert_called_with(
                        '[CIELO24 TRANSCRIPTS] Request failed for video=%s -- lang=%s -- job_id=%s -- message=%s',
                        REQUEST_PARAMS['video_id'],
                        REQUEST_PARAMS['lang_code'],
                        REQUEST_PARAMS['job_id']
                    )

            self.assertEqual(
                s3_exception.exception.message,
                s3_message
            )
