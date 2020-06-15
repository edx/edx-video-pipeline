"""
Cielo24 transcription testing
"""


import json

from django.test import TestCase

import responses
import six.moves.urllib.parse
from ddt import ddt
from mock import patch

from control.veda_deliver_cielo import Cielo24Transcript
from VEDA_OS01.models import (Cielo24Fidelity, Cielo24Turnaround, Course,
                              TranscriptProcessMetadata, TranscriptStatus,
                              Video)
from VEDA.utils import build_url
from VEDA_OS01.transcripts import CIELO24_API_VERSION

VIDEO_DATA = {
    'studio_id': '12345',
    'source_language': 'en'
}


@ddt
class Cielo24TranscriptTests(TestCase):
    """
    Cielo24 transcription tests
    """
    def setUp(self):
        """
        Tests setup
        """
        self.course = Course.objects.create(
            course_name='Intro to VEDA',
            institution='MAx',
            edx_classid='123'
        )

        self.video = Video.objects.create(
            inst_class=self.course,
            **VIDEO_DATA
        )

        self.video_transcript_preferences = {
            'org': 'MAx',
            'api_key': 'cielo24_api_key',
            'turnaround': Cielo24Turnaround.PRIORITY,
            'fidelity': Cielo24Fidelity.PROFESSIONAL,
            'preferred_languages': ['en', 'ur'],
            's3_video_url': 'https://s3.amazonaws.com/bkt/video.mp4',
            'callback_base_url': 'https://veda.edx.org/cielo24/transcript_completed/1234567890',
            'cielo24_api_base_url': 'https://sandbox.cielo24.com/api',
        }

    def tearDown(self):
        """
        Test cleanup
        """
        TranscriptProcessMetadata.objects.all().delete()

    def cielo24_url(self, cielo24, endpoint):
        """
        Return absolute url

        Arguments:
            cielo24 (Cielo24Transcript), object
            endpoint (srt): url endpoint

        Returns:
            absolute url
        """
        return build_url(cielo24.cielo24_api_base_url, endpoint)

    def assert_request(self, received_request, expected_request):
        """
        Verify that `received_request` matches `expected_request`
        """
        expected_parsed_url = six.moves.urllib.parse.urlparse(expected_request['url'])
        expected_request_url = '{scheme}://{netloc}/{path}'.format(
            scheme=expected_parsed_url.scheme, netloc=expected_parsed_url.netloc, path=expected_parsed_url.path
        )
        expected_request_params = dict(six.moves.urllib.parse.parse_qsl(expected_parsed_url.query))

        received_parsed_url = six.moves.urllib.parse.urlparse(received_request.url)
        received_request_url = '{scheme}://{netloc}/{path}'.format(
            scheme=received_parsed_url.scheme, netloc=received_parsed_url.netloc, path=received_parsed_url.path
        )
        received_request_params = dict(six.moves.urllib.parse.parse_qsl(received_parsed_url.query))

        self.assertEqual(received_request.method, expected_request['method'])
        self.assertEqual(received_request_url, expected_request_url)
        self.assertDictEqual(received_request_params, expected_request_params)
        self.assertEqual(received_request.body, expected_request['body'])

    @responses.activate
    def test_transcript_flow(self):
        """
        Verify cielo24 transcription flow
        """
        job_id = '000-111-222'

        cielo24 = Cielo24Transcript(
            video=self.video,
            **self.video_transcript_preferences
        )

        responses.add(
            responses.GET,
            self.cielo24_url(cielo24, cielo24.cielo24_new_job),
            body=json.dumps({'JobId': job_id}),
            status=200
        )
        responses.add(
            responses.GET,
            self.cielo24_url(cielo24, cielo24.cielo24_add_media),
            body=json.dumps({'TaskId': '000-000-111'}),
            status=200
        )
        responses.add(
            responses.GET,
            self.cielo24_url(cielo24, cielo24.cielo24_perform_transcription),
            body=json.dumps({'TaskId': '000-000-000'}),
            status=200
        )

        cielo24.start_transcription_flow()

        # Total of 6 HTTP requests are made
        # 3 cielo24 requests for first language(en)
        # 3 cielo24 requests for second language(ur)
        self.assertEqual(len(responses.calls), 6)

        # pylint: disable=line-too-long
        expected_data = [
            {
                'url': build_url(
                    'https://sandbox.cielo24.com/api/job/new',
                    v=CIELO24_API_VERSION,
                    job_name='12345',
                    language='en',  # A job's language.
                    api_token='cielo24_api_key',
                ),
                'body': None,
                'method': 'GET'
            },
            {
                'url': build_url(
                    'https://sandbox.cielo24.com/api/job/add_media',
                    v=CIELO24_API_VERSION,
                    job_id='000-111-222',
                    api_token='cielo24_api_key',
                    media_url='https://s3.amazonaws.com/bkt/video.mp4',
                ),
                'body': None,
                'method': 'GET',
            },
            {
                'url': build_url(
                    'https://sandbox.cielo24.com/api/job/perform_transcription',
                    v=CIELO24_API_VERSION,
                    job_id='000-111-222',
                    target_language='TARGET_LANG',
                    callback_url='{}?job_id={}&iwp_name={}&lang_code={}&org={}&video_id={}'.format(
                        'https://veda.edx.org/cielo24/transcript_completed/1234567890',
                        '000-111-222',
                        '{iwp_name}',
                        'TARGET_LANG',
                        'MAx',
                        '12345',
                    ),
                    api_token='cielo24_api_key',
                    priority='PRIORITY',
                    transcription_fidelity='PROFESSIONAL',
                    options='{"return_iwp": ["FINAL"]}'
                ),
                'body': None,
                'method': 'GET'
            }
        ]

        received_request_index = 0
        for preferred_language in self.video_transcript_preferences['preferred_languages']:
            for request_data in expected_data:
                # replace target language with appropriate value
                if 'api/job/perform_transcription' in request_data['url']:
                    request_data = dict(request_data)
                    request_data['url'] = request_data['url'].replace('TARGET_LANG', preferred_language)

                self.assert_request(
                    responses.calls[received_request_index].request,
                    request_data
                )
                received_request_index += 1

    @patch('control.veda_deliver_cielo.LOGGER')
    @responses.activate
    def test_transcript_flow_exceptions(self, mock_logger):
        """
        Verify that cielo24 transcription flow works as expected in case of bad response from cielo24
        """
        job_id = '010-010-010'
        bad_request_message = 'Bad request data'

        preferences = dict(self.video_transcript_preferences)
        preferences['preferred_languages'] = ['en']
        cielo24 = Cielo24Transcript(
            video=self.video,
            **preferences
        )

        responses.add(
            responses.GET,
            self.cielo24_url(cielo24, cielo24.cielo24_new_job),
            body=json.dumps({'JobId': job_id}),
            status=200
        )
        responses.add(
            responses.GET,
            self.cielo24_url(cielo24, cielo24.cielo24_add_media),
            body=bad_request_message,
            status=400
        )

        cielo24.start_transcription_flow()

        mock_logger.exception.assert_called_with(
            '[CIELO24] Request failed for video=%s -- lang=%s -- job_id=%s',
            self.video.studio_id,
            preferences['preferred_languages'][0],
            job_id
        )

        # Total of 2 HTTP requests are made for2 cielo24
        self.assertEqual(len(responses.calls), 2)

        process_metadata = TranscriptProcessMetadata.objects.all()
        self.assertEqual(process_metadata.count(), 1)
        self.assertEqual(process_metadata.first().status, TranscriptStatus.FAILED)
