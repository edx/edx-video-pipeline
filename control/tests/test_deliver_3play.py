"""
3PlayMedia transcription unit tests
"""
import json
import urllib
import responses

from ddt import ddt, data, unpack
from mock import patch

from django.test import TestCase
from control.veda_deliver_3play import (
    ThreePLayMediaClient,
    ThreePlayMediaUrlError,
    ThreePlayMediaPerformTranscriptionError,
)
from VEDA_OS01.models import (
    Course,
    TranscriptProcessMetadata,
    Video,
    ThreePlayTurnaround,
)

VIDEO_DATA = {
    'studio_id': '12345'
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
            'turnaround_level': ThreePlayTurnaround.DEFAULT,
            'callback_url': 'https://veda.edx.org/3playmedia/transcripts/handle/123123?org=MAx&edx_video_id=12345'
        }

    def assert_request(self, received_request, expected_request):
        """
        Verify that `received_request` matches `expected_request`
        """
        for request_attr in expected_request.keys():
            if request_attr == 'headers':
                expected_headers = expected_request[request_attr]
                actual_headers = getattr(received_request, request_attr)
                for attr, expect_value in expected_headers.iteritems():
                    self.assertEqual(actual_headers[attr], expect_value)
            else:
                self.assertEqual(getattr(received_request, request_attr), expected_request[request_attr])

    @responses.activate
    @patch('control.veda_deliver_3play.LOGGER')
    def test_transcription_flow(self, mock_logger):
        """
        Verify 3PlayMedia happy transcription flow
        """
        three_play_client = ThreePLayMediaClient(**self.video_transcript_preferences)

        responses.add(
            responses.HEAD,
            u'https://s3.amazonaws.com/bkt/video.mp4',
            headers={'Content-Type': u'video/mp4'},
            status=200,
        )

        responses.add(
            responses.POST,
            u'https://api.3playmedia.com/files',
            body=u'111222',
            status=200
        )

        three_play_client.generate_transcripts()

        # Total of 2 HTTP requests are made
        self.assertEqual(len(responses.calls), 2)

        body = dict(
            # Mandatory attributes required for transcription
            link=self.video_transcript_preferences['media_url'],
            apikey=self.video_transcript_preferences['api_key'],
            api_secret_key=self.video_transcript_preferences['api_secret'],
            turnaround_level=self.video_transcript_preferences['turnaround_level'],
            callback_url=self.video_transcript_preferences['callback_url'],
        )

        expected_requests = [
            {
                'url': u'https://s3.amazonaws.com/bkt/video.mp4',
                'body': None,
                'method': 'HEAD',
            },
            {
                'url': u'https://api.3playmedia.com/files',
                'body': json.dumps(body),
                'method': 'POST',
                'headers': {'Content-Type': 'application/json'}
            },
        ]

        for position, expected_request in enumerate(expected_requests):
            self.assert_request(responses.calls[position].request, expected_request)

        self.assertEqual(TranscriptProcessMetadata.objects.count(), 1)

        mock_logger.info.assert_called_with(
            '[3PlayMedia] Transcription process has been started for video=%s, language=en.',
            VIDEO_DATA['studio_id'],
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
        three_play_client = ThreePLayMediaClient(**self.video_transcript_preferences)
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
        responses.add(responses.POST, u'https://api.3playmedia.com/files', **response)

        three_play_client = ThreePLayMediaClient(**self.video_transcript_preferences)
        with self.assertRaises(ThreePlayMediaPerformTranscriptionError):
            three_play_client.submit_media()

    @data(
        (
            {
                'body': None,
                'status': 400,
            },
            {
                'body': '11111',
                'status': 200,
            },
        ),
        (
            {
                'headers': {'Content-Type': u'video/mp4'},
                'status': 200,
            },
            {
                'body': None,
                'status': 400,
            },
        )
    )
    @unpack
    @responses.activate
    @patch('control.veda_deliver_3play.LOGGER')
    def test_generate_transcripts_exceptions(self, first_response, second_response, mock_log):
        """
        Tests the proper exceptions during transcript generation.
        """
        responses.add(responses.HEAD, u'https://s3.amazonaws.com/bkt/video.mp4', **first_response)
        responses.add(responses.POST, u'https://api.3playmedia.com/files', **second_response)
        three_play_client = ThreePLayMediaClient(**self.video_transcript_preferences)
        three_play_client.generate_transcripts()

        self.assertFalse(mock_log.info.called)
        mock_log.exception.assert_called_with(
            u'[3PlayMedia] Could not process transcripts for video=%s language=en.',
            VIDEO_DATA['studio_id'],
        )
        self.assertEqual(TranscriptProcessMetadata.objects.count(), 0)
