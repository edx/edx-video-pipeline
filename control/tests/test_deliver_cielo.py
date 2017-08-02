"""
Cielo24 transcription testing
"""
from unittest import TestCase

import responses
from ddt import ddt
from mock import patch

from control.veda_deliver_cielo import Cielo24Transcript
from VEDA_OS01.models import (Cielo24Fidelity, Cielo24Turnaround, Course,
                              TranscriptProcessMetadata, TranscriptStatus,
                              Video)
from VEDA_OS01.utils import build_url

CONFIG_DATA = {
    'cielo24_get_caption_url': 'http://api.cielo24.com/job/get_caption',
    'transcript_bucket_access_key': 'bucket_access_key',
    'transcript_bucket_secret_key': 'bucket_secret_key',
    'transcript_bucket_name': 'bucket_name',
    'val_token_url': 'http://val.edx.org/token',
    'val_username': 'username',
    'val_password': 'password',
    'val_client_id': 'client',
    'val_secret_key': 'secret',
    'val_transcript_create_url': 'http://val.edx.org/transcript/create',
    'val_video_transcript_status_url': 'http://val.edx.org/video/status',
    'veda_base_url': 'https://veda.edx.org',
    'transcript_provider_request_token': '1234a5a67cr890'
}

VIDEO_DATA = {
    'studio_id': '12345'
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
        return build_url(cielo24.cielo24_site, endpoint)

    def assert_request(self, received_request, expected_request):
        """
        Verify that `received_request` matches `expected_request`
        """
        self.assertEqual(received_request.method, expected_request['method'])
        self.assertEqual(received_request.url, expected_request['url'])
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
            body={'JobId': job_id},
            status=200
        )
        responses.add(
            responses.GET,
            self.cielo24_url(cielo24, cielo24.cielo24_add_media),
            body={'TaskId': '000-000-111'},
            status=200
        )
        responses.add(
            responses.GET,
            self.cielo24_url(cielo24, cielo24.cielo24_perform_transcription),
            body={'TaskId': '000-000-000'},
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
                'url': 'https://api.cielo24.com/api/job/new?api_token=cielo24_api_key&job_name=12345&language=en&v=1',
                'body': None,
                'method': 'GET'
            },
            {
                'url': 'https://api.cielo24.com/api/job/add_media?media_url=https%253A%252F%252Fs3.amazonaws.com%252Fbkt%252Fvideo.mp4&api_token=cielo24_api_key&job_id=000-111-222&v=1',
                'body': None,
                'method': 'GET'
            },
            {
                'url': 'https://api.cielo24.com/api/job/perform_transcription?transcription_fidelity=PROFESSIONAL&job_id=000-111-222&v=1&priority=PRIORITY&api_token=cielo24_api_key&callback_url=https%253A%252F%252Fveda.edx.org%252Fcielo24%252Ftranscript_completed%252F1234567890%253Flang_code%253D{}%2526video_id%253D12345%2526job_id%253D000-111-222%2526org%253DMAx&target_language={}',
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
                    request_data['url'] = request_data['url'].format(preferred_language, preferred_language)

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
            body={'JobId': job_id},
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
