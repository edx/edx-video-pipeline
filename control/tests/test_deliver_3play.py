"""
3PlayMedia transcription unit tests
"""

import json
import responses

from ddt import ddt, data, unpack
from mock import Mock, patch

from django.test import TestCase
from control.veda_deliver_3play import (
    ThreePlayMediaClient,
    ThreePlayMediaUrlError,
    ThreePlayMediaPerformTranscriptionError,
)
from VEDA_OS01.models import (
    Course,
    TranscriptProcessMetadata,
    Video,
    ThreePlayTurnaround,
)
from VEDA.utils import build_url
import six

VIDEO_DATA = {
    'studio_id': '12345',
    'source_language': 'en'
}


@ddt
class ThreePlayMediaClientTests(TestCase):
    """
    3PlayMedia transcription tests
    """
    def setUp(self):
        """
        Tests setup
        """
        self.course = Course.objects.create(
            course_name=u'Intro to VEDA',
            institution=u'MAx',
            edx_classid=u'123'
        )

        self.video = Video.objects.create(
            inst_class=self.course,
            **VIDEO_DATA
        )

        self.video_transcript_preferences = {
            'org': u'MAx',
            'video': self.video,
            'media_url': u'https://s3.amazonaws.com/bkt/video.mp4',
            'api_key': u'insecure_api_key',
            'api_secret': u'insecure_api_secret',
            'turnaround_level': ThreePlayTurnaround.STANDARD,
            'callback_url': build_url(
                u'https://veda.edx.org/3playmedia/transcripts/handle/123123',
                org=u'MAx',
                edx_video_id=VIDEO_DATA['studio_id'],
                lang_code=VIDEO_DATA['source_language'],
            ),
            'three_play_api_base_url': 'https://api.3playmedia.com/',
        }

    def assert_request(self, received_request, expected_request, decode_func):
        """
        Verify that `received_request` matches `expected_request`
        """
        for request_attr in expected_request.keys():
            if request_attr == 'headers':
                expected_headers = expected_request[request_attr]
                actual_headers = getattr(received_request, request_attr)
                for attr, expect_value in six.iteritems(expected_headers):
                    self.assertEqual(actual_headers[attr], expect_value)
            elif request_attr == 'body' and decode_func:
                self.assertDictEqual(decode_func(received_request.body), expected_request[request_attr])
            else:
                self.assertEqual(getattr(received_request, request_attr), expected_request[request_attr])

    @responses.activate
    @patch('control.veda_deliver_3play.LOGGER')
    def test_transcription_flow(self, mock_logger):
        """
        Verify 3PlayMedia happy transcription flow
        """
        three_play_client = ThreePlayMediaClient(**self.video_transcript_preferences)

        responses.add(
            responses.HEAD,
            u'https://s3.amazonaws.com/bkt/video.mp4',
            headers={'Content-Type': u'video/mp4'},
            status=200,
        )

        responses.add(
            responses.GET,
            u'https://api.3playmedia.com/caption_imports/available_languages',
            body=json.dumps([{
                "iso_639_1_code": "en",
                "language_id": 1,
            }]),
            status=200,
        )

        responses.add(
            responses.POST,
            u'https://api.3playmedia.com/files',
            body=u'111222',
            status=200
        )

        three_play_client.generate_transcripts()

        # Total of 3 HTTP requests are made
        self.assertEqual(len(responses.calls), 3)

        body = dict(
            # Mandatory attributes required for transcription
            link=self.video_transcript_preferences['media_url'],
            apikey=self.video_transcript_preferences['api_key'],
            api_secret_key=self.video_transcript_preferences['api_secret'],
            turnaround_level=self.video_transcript_preferences['turnaround_level'],
            callback_url=self.video_transcript_preferences['callback_url'],
            language_id=1,
            batch_name='Default',
        )

        expected_requests = [
            {
                'url': u'https://s3.amazonaws.com/bkt/video.mp4',
                'body': None,
                'method': 'HEAD',
            },
            {
                'url': u'https://api.3playmedia.com/caption_imports/available_languages?apikey=insecure_api_key',
                'body': None,
                'method': 'GET',
            },
            {
                'url': u'https://api.3playmedia.com/files',
                'body': body,
                'method': 'POST',
                'headers': {'Content-Type': 'application/json'},
                'decode_func': json.loads
            },
        ]

        for position, expected_request in enumerate(expected_requests):
            self.assert_request(
                received_request=responses.calls[position].request,
                expected_request=expected_request,
                decode_func=expected_request.pop('decode_func', None)
            )

        self.assertEqual(TranscriptProcessMetadata.objects.count(), 1)

        mock_logger.info.assert_called_with(
            '[3PlayMedia] Transcription process has been started for video=%s, source_language=%s.',
            VIDEO_DATA['studio_id'],
            VIDEO_DATA['source_language'],
        )

    @data(
        {
            'headers': {'Content-Type': u'video/mp4'},
            'status': 400,
        },
        {
            'headers': {'Content-Type': u'application/json'},
            'status': 200,
        }
    )
    @responses.activate
    def test_validate_media_url(self, response):
        """
        Tests media url validations.
        """
        responses.add(responses.HEAD, u'https://s3.amazonaws.com/bkt/video.mp4', **response)
        three_play_client = ThreePlayMediaClient(**self.video_transcript_preferences)
        with self.assertRaises(ThreePlayMediaUrlError):
            three_play_client.validate_media_url()

    @data(
        {
            'body': None,
            'status': 400,
        },
        {
            'body': json.dumps({'iserror': True, 'error': 'Submission has failed'}),
            'status': 200,
        }
    )
    @responses.activate
    def test_submit_media_exceptions(self, response):
        """
        Tests media submission exceptions
        """
        responses.add(
            responses.HEAD,
            u'https://s3.amazonaws.com/bkt/video.mp4',
            headers={'Content-Type': u'video/mp4'},
            status=200,
        )
        responses.add(responses.GET, u'https://api.3playmedia.com/caption_imports/available_languages', **{
            'status': 200,
            'body': json.dumps([{
                "iso_639_1_code": "en",
                "language_id": 1,
            }])
        })
        responses.add(responses.POST, u'https://api.3playmedia.com/files', **response)

        three_play_client = ThreePlayMediaClient(**self.video_transcript_preferences)
        with self.assertRaises(ThreePlayMediaPerformTranscriptionError):
            three_play_client.submit_media()

    @data(
        (
            # Error
            {
                'body': None,
                'status': 400,
            },
            # Success
            {
                'body': '[{"iso_639_1_code": "en", "language_id": 1}]',
                'status': 200,
            },
            # Success
            {
                'body': '11111',
                'status': 200,
            },
        ),
        (
            # Success
            {
                'headers': {'Content-Type': u'video/mp4'},
                'status': 200,
            },
            # Error
            {
                'body': None,
                'status': 400,
            },
            # Success
            {
                'body': '11111',
                'status': 200,
            },
        ),
        (
            # Success
            {
                'headers': {'Content-Type': u'video/mp4'},
                'status': 200,
            },
            # Error
            {
                'body': '{"error": "unauthorized"}',
                'status': 200,
            },
            # Success
            {
                'body': '11111',
                'status': 200,
            },
        ),
        (
            # Success
            {
                'headers': {'Content-Type': u'video/mp4'},
                'status': 200,
            },
            # Success
            {
                'body': '[{"iso_639_1_code": "en", "language_id": 1}]',
                'status': 200,
            },
            # Error
            {
                'body': None,
                'status': 400,
            },
        ),
        (
            # Success
            {
                'headers': {'Content-Type': u'video/mp4'},
                'status': 200,
            },
            # Success
            {
                'body': '[{"iso_639_1_code": "en", "language_id": 1}]',
                'status': 200,
            },
            # Error
            {
                'body': '{"error": "unauthorized"}',
                'status': 200,
            },
        )
    )
    @unpack
    @responses.activate
    @patch('control.veda_deliver_3play.LOGGER')
    def test_generate_transcripts_exceptions(self, first_response, second_response, third_response, mock_log):
        """
        Tests the proper exceptions during transcript generation.
        """
        responses.add(responses.HEAD, u'https://s3.amazonaws.com/bkt/video.mp4', **first_response)
        responses.add(
            responses.GET, u'https://api.3playmedia.com/caption_imports/available_languages', **second_response
        )
        responses.add(responses.POST, u'https://api.3playmedia.com/files', **third_response)
        three_play_client = ThreePlayMediaClient(**self.video_transcript_preferences)
        three_play_client.generate_transcripts()

        self.assertFalse(mock_log.info.called)
        mock_log.exception.assert_called_with(
            u'[3PlayMedia] Could not process transcripts for video=%s source_language=%s.',
            VIDEO_DATA['studio_id'],
            VIDEO_DATA['source_language'],
        )
        self.assertEqual(TranscriptProcessMetadata.objects.count(), 0)

    @patch('control.veda_deliver_3play.LOGGER')
    @patch('control.veda_deliver_3play.ThreePlayMediaClient.submit_media', Mock(side_effect=ValueError))
    def test_generate_transcripts_unknown_exceptions(self, mock_log):
        """
        Verify that the unknown exceptions are logged during transcript generation.
        """
        three_play_client = ThreePlayMediaClient(**self.video_transcript_preferences)

        with self.assertRaises(ValueError):
            three_play_client.generate_transcripts()

        self.assertFalse(mock_log.info.called)
        mock_log.exception.assert_called_with(
            u'[3PlayMedia] Unexpected error while transcription for video=%s source_language=%s.',
            VIDEO_DATA['studio_id'],
            VIDEO_DATA['source_language'],
        )
        self.assertEqual(TranscriptProcessMetadata.objects.count(), 0)
