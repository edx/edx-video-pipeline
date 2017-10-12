# -*- encoding: utf-8 -*-
"""
Transcript tests
"""
import json
import responses
import urllib
import urlparse

from boto.exception import S3ResponseError
from boto.s3.connection import S3Connection
from boto.s3.key import Key
from ddt import data, ddt, unpack
from django.core.urlresolvers import reverse
from mock import Mock, PropertyMock, patch
from moto import mock_s3_deprecated
from rest_framework import status
from rest_framework.test import APITestCase

from VEDA_OS01 import transcripts, utils
from VEDA_OS01.models import (Course, TranscriptCredentials,
                              TranscriptProcessMetadata, TranscriptProvider,
                              TranscriptStatus, Video)

CONFIG_DATA = utils.get_config('test_config.yaml')

VIDEO_DATA = {
    'studio_id': '12345',
    'preferred_languages': ['en']
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

REQUEST_PARAMS = {'job_id': 100, 'iwp_name': 'FINAL', 'lang_code': 'en', 'org': 'MAx', 'video_id': '111'}

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

        self.transcript_prefs = TranscriptCredentials.objects.create(
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
            'status': utils.ValTranscriptStatus.TRANSCRIPT_READY,
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
        ('cielo24/transcript_completed', 404),
        (None, 200),
    )
    @unpack
    @patch('VEDA_OS01.transcripts.CIELO24_TRANSCRIPT_COMPLETED.send_robust', Mock(return_value=None))
    def test_provider(self, url, status_code):
        """
        Verify that only valid provider requests are allowed .
        """
        response = self.client.get(
            url or self.url,
            {'job_id': 3, 'iwp_name': 'FINAL', 'lang_code': 'ar', 'org': 'edx', 'video_id': 12345}
        )
        self.assertEqual(response.status_code, status_code)

    @data(
        ({}, ['job_id', 'iwp_name', 'lang_code', 'org', 'video_id']),
        ({'job_id': 1}, ['iwp_name', 'lang_code', 'org', 'video_id']),
        ({'job_id': 2, 'lang_code': 'en'}, ['iwp_name', 'org', 'video_id']),
        ({'job_id': 3, 'lang_code': 'ar', 'org': 'edx'}, ['iwp_name', 'video_id']),
    )
    @unpack
    @patch('VEDA_OS01.transcripts.LOGGER')
    def test_missing_required_params(self, params, logger_params, mock_logger):
        """
        Verify that 400 response is recevied if any required param is missing.
        """
        response = self.client.get(self.url, params)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        mock_logger.warning.assert_called_with(
            '[CIELO24 HANDLER] Required params are missing %s',
            logger_params,
        )

    @responses.activate
    @patch('VEDA_OS01.transcripts.CIELO24_TRANSCRIPT_COMPLETED.send_robust', Mock(return_value=None))
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
    @patch('VEDA_OS01.transcripts.LOGGER')
    @responses.activate
    @mock_s3_deprecated
    def test_cielo24_callback(self, mock_logger):
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

        # Assert the logs.
        mock_logger.info.assert_called_with(
            '[CIELO24 TRANSCRIPTS] Transcript complete request received for '
            'video=%s -- org=%s -- lang=%s -- job_id=%s -- iwp_name=%s',
            REQUEST_PARAMS['video_id'],
            REQUEST_PARAMS['org'],
            REQUEST_PARAMS['lang_code'],
            REQUEST_PARAMS['job_id'],
            REQUEST_PARAMS['iwp_name']
        )
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

        # Assert edx-video-pipeline's video status
        video = Video.objects.get(studio_id=self.video.studio_id)
        self.assertEqual(video.transcript_status, TranscriptStatus.READY)

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
                    '[CIELO24 TRANSCRIPTS] Request failed for video=%s -- lang=%s -- job_id=%s.',
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


@ddt
@patch.dict('VEDA_OS01.transcripts.CONFIG', CONFIG_DATA)
@patch('VEDA_OS01.transcripts.VALAPICall._AUTH', PropertyMock(return_value=lambda: CONFIG_DATA))
class ThreePlayTranscriptionCallbackTest(APITestCase):
    """
    3Play Media callback tests
    """
    def setUp(self):
        """
        Tests setup.
        """
        super(ThreePlayTranscriptionCallbackTest, self).setUp()

        self.org = u'MAx'
        self.file_id = u'112233'
        self.video_source_language = u'en'
        self.edx_video_id = VIDEO_DATA['studio_id']

        self.url = reverse('3play_media_callback', args=[CONFIG_DATA['transcript_provider_request_token']])

        self.course = Course.objects.create(
            course_name='Intro to VEDA',
            institution=self.org,
            edx_classid='123',
            local_storedir='course-v1:MAx+123+test_run',
        )
        self.video = Video.objects.create(
            inst_class=self.course,
            source_language=self.video_source_language,
            provider=TranscriptProvider.THREE_PLAY,
            transcript_status=TranscriptStatus.IN_PROGRESS,
            **VIDEO_DATA
        )

        self.transcript_prefs = TranscriptCredentials.objects.create(
            org=self.org,
            provider=TranscriptProvider.THREE_PLAY,
            api_key='insecure_api_key',
            api_secret='insecure_api_secret'
        )

        TranscriptProcessMetadata.objects.create(
            video=self.video,
            process_id=self.file_id,
            lang_code='en',
            provider=TranscriptProvider.THREE_PLAY,
            status=TranscriptStatus.IN_PROGRESS,
        )

        self.uuid_hex = '01234567890123456789'
        uuid_patcher = patch.object(
            transcripts.uuid.UUID,
            'hex',
            new_callable=PropertyMock(return_value=self.uuid_hex)
        )
        uuid_patcher.start()
        self.addCleanup(uuid_patcher.stop)

    def setup_s3_bucket(self):
        """
        Creates an s3 bucket. That is happening in moto's virtual environment.
        """
        connection = S3Connection()
        connection.create_bucket(CONFIG_DATA['aws_video_transcripts_bucket'])
        return connection

    def invoke_3play_callback(self, state='complete'):
        """
        Make request to 3PlayMedia callback handler, this invokes
        callback with all the necessary parameters.

        Arguments:
            state(str): state of the callback
        """
        response = self.client.post(
            # `build_url` strips `/`, putting it back and add necessary query params.
            '/{}'.format(utils.build_url(
                self.url, edx_video_id=self.video.studio_id,
                org=self.org, lang_code=self.video_source_language
            )),
            content_type='application/x-www-form-urlencoded',
            data=urllib.urlencode(dict(file_id=self.file_id, status=state))
        )
        return response

    def setup_translations_prereqs(self, file_id, translation_lang_map, preferred_languages):
        """
        Sets up pre-requisites for 3Play Media translations retrieval process.
        """
        # Update preferred languages.
        self.video.preferred_languages = preferred_languages
        self.video.save()

        # Assumes the speech transcript is ready.
        TranscriptProcessMetadata.objects.filter(
            process_id=self.file_id,
            lang_code=self.video_source_language,
        ).update(status=TranscriptStatus.READY)

        # Create translation processes and set their statuses to 'IN PROGRESS'.
        for target_language, translation_id in translation_lang_map.iteritems():
            # Create translation processes for all the target languages.
            TranscriptProcessMetadata.objects.create(
                video=self.video,
                provider=TranscriptProvider.THREE_PLAY,
                process_id=file_id,
                translation_id=translation_id,
                lang_code=target_language,
                status=TranscriptStatus.IN_PROGRESS,
            )

    def assert_request(self, received_request, expected_request, decode_func):
        """
        Verify that `received_request` matches `expected_request`
        """
        for request_attr in expected_request.keys():
            if request_attr == 'headers':
                expected_headers = expected_request[request_attr]
                actual_headers = getattr(received_request, request_attr)
                for attr, expect_value in expected_headers.iteritems():
                    self.assertEqual(actual_headers[attr], expect_value)
            elif request_attr == 'body' and decode_func:
                expected_body = expected_request[request_attr]
                actual_body = decode_func(getattr(received_request, request_attr))
                for attr, expect_value in expected_body.iteritems():
                    self.assertEqual(actual_body[attr], expect_value)
            else:
                self.assertEqual(getattr(received_request, request_attr), expected_request[request_attr])

    def assert_uploaded_transcript_on_s3(self, connection):
        """
        Verify sjson data uploaded to s3
        """
        key = Key(connection.get_bucket(CONFIG_DATA['aws_video_transcripts_bucket']))
        key.key = '{directory}{uuid}.sjson'.format(
            directory=CONFIG_DATA['aws_video_transcripts_prefix'], uuid=self.uuid_hex
        )
        sjson_transcript = json.loads(key.get_contents_as_string())
        self.assertEqual(sjson_transcript, TRANSCRIPT_SJSON_DATA)

    def test_unauthorized_access_to_3play_callback(self):
        """
        Tests that the invalid token leads to 401 Unauthorized Response
        """
        self.url = reverse('3play_media_callback', args=['123invalidtoken456'])
        response = self.client.post(self.url, content_type='application/x-www-form-urlencoded')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    @data(
        {'data': {}, 'query_params': {}},
        {'data': {'file_id': '1122'}, 'query_params': {'edx_video_id': '1234'}}
    )
    @patch('VEDA_OS01.transcripts.LOGGER')
    def test_missing_required_params(self, request_data, mock_logger):
        """
        Test the callback in case of missing attributes.
        """
        response = self.client.post(
            '/{}'.format(utils.build_url(self.url, **request_data['query_params'])),
            content_type='application/x-www-form-urlencoded',
            data=urllib.urlencode(request_data['data']),
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Assert the logs
        required_attrs = ['file_id', 'lang_code', 'status', 'org', 'edx_video_id']
        received_attrs = request_data['data'].keys() + request_data['query_params'].keys()
        missing_attrs = [attr for attr in required_attrs if attr not in received_attrs]
        mock_logger.warning.assert_called_with(
            u'[3PlayMedia Callback] process_id=%s Received Attributes=%s Missing Attributes=%s',
            request_data['data'].get('file_id', None),
            received_attrs,
            missing_attrs,
        )

    @data(
        (
            u'error',
            u'[3PlayMedia Callback] Error while transcription - error=%s, org=%s, edx_video_id=%s, file_id=%s.',
            TranscriptStatus.FAILED
        ),
        (
            u'invalid_status',
            u'[3PlayMedia Callback] Got invalid status - status=%s, org=%s, edx_video_id=%s, file_id=%s.',
            TranscriptStatus.IN_PROGRESS
        )
    )
    @unpack
    @responses.activate
    @patch('VEDA_OS01.transcripts.LOGGER')
    def test_callback_for_non_success_statuses(self, state, message, expected_status, mock_logger):
        """
        Tests the callback for all the non-success statuses.
        """
        self.url = '/{}'.format(utils.build_url(
            self.url, edx_video_id='12345', org='MAx', lang_code=self.video_source_language
        ))
        self.client.post(self.url, content_type='application/x-www-form-urlencoded', data=urllib.urlencode({
            'file_id': self.file_id,
            'status': state,
            'error_description': state  # this will be logged.
        }))

        self.assertEqual(
            TranscriptProcessMetadata.objects.filter(process_id=self.file_id).latest().status,
            expected_status
        )
        mock_logger.error.assert_called_with(
            message,
            state,
            self.org,
            self.video.studio_id,
            self.file_id
        )

    @responses.activate
    @mock_s3_deprecated
    @patch('VEDA_OS01.transcripts.LOGGER')
    def test_single_lang_callback_flow(self, mock_logger):
        """
        Tests 3Play Media callback works as expected.
        """
        # Setup an s3 bucket
        conn = self.setup_s3_bucket()
        # 3Play mocked response
        responses.add(
            responses.GET,
            transcripts.THREE_PLAY_TRANSCRIPT_URL.format(file_id=self.file_id),
            body=TRANSCRIPT_SRT_DATA,
            content_type='text/plain; charset=utf-8',
            status=200
        )

        # edx-val mocked responses
        responses.add(responses.POST, CONFIG_DATA['val_token_url'], '{"access_token": "1234567890"}', status=200)
        responses.add(responses.POST, CONFIG_DATA['val_transcript_create_url'], status=200)
        responses.add(responses.PATCH, CONFIG_DATA['val_video_transcript_status_url'], status=200)

        # Make request to callback
        response = self.invoke_3play_callback()

        # Assert the response and the process
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            TranscriptProcessMetadata.objects.filter(process_id=self.file_id).latest().status,
            TranscriptStatus.READY
        )

        # Total of 4 HTTP requests are made as registered above
        self.assertEqual(len(responses.calls), 4)

        expected_requests = [
            # request - 1
            {
                'url': utils.build_url(
                    transcripts.THREE_PLAY_TRANSCRIPT_URL.format(file_id=self.file_id),
                    apikey=self.transcript_prefs.api_key
                )
            },
            # request - 2
            {
                'url': CONFIG_DATA['val_token_url'],
                'body': {
                    'grant_type': ['password'],
                    'client_id': [CONFIG_DATA['val_client_id']],
                    'client_secret': [CONFIG_DATA['val_secret_key']],
                    'username': [CONFIG_DATA['val_username']],
                    'password': [CONFIG_DATA['val_password']],
                },
                'decode_func': urlparse.parse_qs,
            },
            # request - 3
            {
                'url': CONFIG_DATA['val_transcript_create_url'],
                'body': {
                    'file_format': transcripts.TRANSCRIPT_SJSON,
                    'video_id': self.video.studio_id,
                    'language_code': 'en',
                    'name': '{directory}{uuid}.sjson'.format(
                        directory=CONFIG_DATA['aws_video_transcripts_prefix'], uuid=self.uuid_hex
                    ),
                    'provider': TranscriptProvider.THREE_PLAY
                },
                'headers': {
                    'Authorization': 'Bearer 1234567890',
                    'content-type': 'application/json'
                },
                'decode_func': json.loads,
            },
            # request - 4
            {
                'url': CONFIG_DATA['val_video_transcript_status_url'],
                'body': {
                    'status': utils.ValTranscriptStatus.TRANSCRIPT_READY,
                    'edx_video_id': self.video.studio_id
                },
                'headers': {
                    'Authorization': 'Bearer 1234567890',
                    'content-type': 'application/json'
                },
                'decode_func': json.loads,
            }
        ]

        for position, expected_request in enumerate(expected_requests):
            self.assert_request(
                responses.calls[position].request,
                expected_request,
                expected_request.pop('decode_func', None)
            )

        # Assert edx-video-pipeline's video status
        video = Video.objects.get(studio_id=self.video.studio_id)
        self.assertEqual(video.transcript_status, TranscriptStatus.READY)

        # verify transcript sjson data uploaded to s3
        self.assert_uploaded_transcript_on_s3(connection=conn)

        mock_logger.info.assert_called_with(
            u'[3PlayMedia Callback] Video speech transcription was successful for video=%s -- lang_code=%s -- '
            u'process_id=%s',
            self.video.studio_id,
            'en',
            self.file_id,
        )

    @responses.activate
    @mock_s3_deprecated
    @patch('VEDA_OS01.transcripts.LOGGER')
    def test_multi_lang_callback_flow(self, mock_logger):
        """
        Tests 3Play Media callback works as expected.
        """
        conn = self.setup_s3_bucket()
        # Video needs to transcripts in multiple languages
        self.video.preferred_languages = ['en', 'ro']
        self.video.save()
        # 3Play mock translation id
        translation_id = '007-abc'

        # 3Play mocked response
        responses.add(
            responses.GET,
            transcripts.THREE_PLAY_TRANSCRIPT_URL.format(file_id=self.file_id),
            body=TRANSCRIPT_SRT_DATA,
            content_type='text/plain; charset=utf-8',
            status=200
        )
        responses.add(
            responses.GET,
            transcripts.THREE_PLAY_TRANSLATION_SERVICES_URL,
            json.dumps([
                {
                    'id': 30,
                    'source_language_name': 'English',
                    'source_language_iso_639_1_code': 'en',
                    'target_language_name': 'Romanian',
                    'target_language_iso_639_1_code': 'ro',
                    'service_level': 'standard',
                    'per_word_rate': 0.16
                },
                {
                    'id': 31,
                    'source_language_name': 'English',
                    'source_language_iso_639_1_code': 'en',
                    'target_language_name': 'German',
                    'target_language_iso_639_1_code': 'da',
                    'service_level': 'standard',
                    'per_word_rate': 0.19
                }
            ]),
            status=200,
        )
        responses.add(
            responses.POST,
            transcripts.THREE_PLAY_ORDER_TRANSLATION_URL.format(file_id=self.file_id),
            json.dumps({
                'success': True,
                'translation_id': translation_id
            }),
            status=200,
        )

        # edx-val mocked responses
        responses.add(responses.POST, CONFIG_DATA['val_token_url'], '{"access_token": "1234567890"}', status=200)
        responses.add(responses.POST, CONFIG_DATA['val_transcript_create_url'], status=200)

        # Make request to callback
        response = self.invoke_3play_callback()

        # Assert the response and the speech lang process
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            TranscriptProcessMetadata.objects.get(
                process_id=self.file_id,
                provider=TranscriptProvider.THREE_PLAY,
                lang_code='en'
            ).status,
            TranscriptStatus.READY
        )

        # Assert the transcript translation process
        self.assertEqual(
            TranscriptProcessMetadata.objects.get(
                process_id=self.file_id,
                provider=TranscriptProvider.THREE_PLAY,
                lang_code='ro'
            ).status,
            TranscriptStatus.IN_PROGRESS,
        )

        # Total of 5 HTTP requests are made as registered above
        self.assertEqual(len(responses.calls), 5)

        expected_requests = [
            # request - 1
            {
                'url': utils.build_url(
                    transcripts.THREE_PLAY_TRANSCRIPT_URL.format(file_id=self.file_id),
                    apikey=self.transcript_prefs.api_key
                )
            },
            # request - 2
            {
                'url': CONFIG_DATA['val_token_url'],
                'body': {
                    'grant_type': ['password'],
                    'client_id': [CONFIG_DATA['val_client_id']],
                    'client_secret': [CONFIG_DATA['val_secret_key']],
                    'username': [CONFIG_DATA['val_username']],
                    'password': [CONFIG_DATA['val_password']],
                },
                'decode_func': urlparse.parse_qs,
            },
            # request - 3
            {
                'url': CONFIG_DATA['val_transcript_create_url'],
                'body': {
                    'file_format': transcripts.TRANSCRIPT_SJSON,
                    'video_id': self.video.studio_id,
                    'language_code': 'en',
                    'name': '{directory}{uuid}.sjson'.format(
                        directory=CONFIG_DATA['aws_video_transcripts_prefix'], uuid=self.uuid_hex
                    ),
                    'provider': TranscriptProvider.THREE_PLAY
                },
                'headers': {
                    'Authorization': 'Bearer 1234567890',
                    'content-type': 'application/json'
                },
                'decode_func': json.loads,
            },
            # request - 4
            {
                'url': utils.build_url(
                    transcripts.THREE_PLAY_TRANSLATION_SERVICES_URL,
                    apikey=self.transcript_prefs.api_key
                )
            },
            # request - 5
            {
                'url': transcripts.THREE_PLAY_ORDER_TRANSLATION_URL.format(file_id=self.file_id),
                'body': {
                    'apikey': self.transcript_prefs.api_key,
                    'api_secret_key': self.transcript_prefs.api_secret,
                    'translation_service_id': 30,
                },
                'decode_func': json.loads,
            },
        ]

        for position, expected_request in enumerate(expected_requests):
            self.assert_request(
                responses.calls[position].request,
                expected_request,
                expected_request.pop('decode_func', None),
            )

        # verify sjson data uploaded to s3
        self.assert_uploaded_transcript_on_s3(connection=conn)

        mock_logger.info.assert_called_with(
            u'[3PlayMedia Callback] Video speech transcription was successful for video=%s -- lang_code=%s -- '
            u'process_id=%s',
            self.video.studio_id,
            'en',
            self.file_id,
        )

    @data(
        (
            {'body': json.dumps({'iserror': True}), 'content_type': 'application/json', 'status': 200},
            'error',
            (
                u'[%s] Transcript fetch error for video=%s -- lang_code=%s -- process=%s -- response=%s',
                u'3PlayMedia Callback',
                u'12345',
                u'en',
                u'112233',
                json.dumps({'iserror': True}),
            ),
        ),
        (
            {'body': None, 'status': 400},
            'exception',
            (
                u'[3PlayMedia Callback] Fetch request failed for video=%s -- lang_code=%s -- process_id=%s',
                u'12345',
                u'en',
                u'112233',
            ),
        )
    )
    @unpack
    @responses.activate
    @patch('VEDA_OS01.transcripts.LOGGER')
    def test_fetch_transcript_exceptions(self, response, log_method, log_args, mock_logger):
        """
        Verify the logs if there is an error during transcript fetch.
        """
        # 3Play mocked response
        responses.add(responses.GET, transcripts.THREE_PLAY_TRANSCRIPT_URL.format(file_id=self.file_id), **response)

        # Make request to the callback
        response = self.invoke_3play_callback()

        # Assert the response, process and the logs.
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            TranscriptProcessMetadata.objects.filter(process_id=self.file_id).latest().status,
            TranscriptStatus.FAILED
        )
        getattr(mock_logger, log_method).assert_called_with(*log_args)

    @patch('VEDA_OS01.transcripts.LOGGER')
    @responses.activate
    def test_srt_to_sjson_conversion_exceptions(self, mock_logger):
        """
        Tests that the correct exception is logged on conversion error.
        """
        # 3Play mocked response
        responses.add(
            responses.GET,
            transcripts.THREE_PLAY_TRANSCRIPT_URL.format(file_id=self.file_id),
            body=TRANSCRIPT_SRT_DATA,
            content_type=u'text/plain; charset=utf-8',
            status=200
        )

        # make `convert_srt_to_sjson` to fail with ValueError
        with patch('VEDA_OS01.transcripts.convert_srt_to_sjson') as mock_convert_srt_to_sjson:
            mock_convert_srt_to_sjson.side_effect = ValueError
            # Make request to the callback
            self.invoke_3play_callback()
            mock_logger.exception.assert_called_with(
                u'[3PlayMedia Callback] Request failed for video=%s -- lang_code=%s -- process_id=%s',
                self.video.studio_id,
                'en',
                self.file_id,
            )

    @patch('VEDA_OS01.transcripts.LOGGER')
    @responses.activate
    def test_upload_to_s3_exceptions(self, mock_logger):
        """
        Tests that the correct exception is logged on error while uploading to s3.
        """
        # 3Play mocked response
        responses.add(
            responses.GET,
            transcripts.THREE_PLAY_TRANSCRIPT_URL.format(file_id=self.file_id),
            body=TRANSCRIPT_SRT_DATA,
            content_type=u'text/plain; charset=utf-8',
            status=200
        )
        with patch('VEDA_OS01.transcripts.upload_sjson_to_s3') as mock_upload_sjson_to_s3:
            mock_upload_sjson_to_s3.side_effect = S3ResponseError(status=401, reason='invalid secrets')
            # Make request to the callback
            self.invoke_3play_callback()
            mock_logger.exception.assert_called_with(
                u'[3PlayMedia Callback] Request failed for video=%s -- lang_code=%s -- process_id=%s',
                self.video.studio_id,
                'en',
                self.file_id,
            )

    @data(
        # not-an-ok response on translation services fetch request.
        (
            [
                {
                    'method': responses.GET,
                    'url': transcripts.THREE_PLAY_TRANSLATION_SERVICES_URL,
                    'body': 'Your request was invalid.',
                    'status': 400,
                }
            ],
            {
                'method': 'exception',
                'args': (
                    '[3PlayMedia Callback] Translation could not be performed - video=%s, lang_code=%s, file_id=%s.',
                    '12345',
                    'en',
                    '112233'
                )
            }
        ),
        # Error on 3Play while fetching translation services.
        (
            [
                {
                    'method': responses.GET,
                    'url': transcripts.THREE_PLAY_TRANSLATION_SERVICES_URL,
                    'body': json.dumps({
                        'success': False
                    }),
                    'status': 200,
                }
            ],
            {
                'method': 'exception',
                'args': (
                    '[3PlayMedia Callback] Translation could not be performed - video=%s, lang_code=%s, file_id=%s.',
                    '12345',
                    'en',
                    '112233'
                )
            }
        ),
        # not-an-ok response on translation order request.
        (
            [
                {
                    'method': responses.GET,
                    'url': transcripts.THREE_PLAY_TRANSLATION_SERVICES_URL,
                    'body': json.dumps(
                        [{
                            'id': 30,
                            'source_language_name': 'English',
                            'source_language_iso_639_1_code': 'en',
                            'target_language_name': 'Romanian',
                            'target_language_iso_639_1_code': 'ro',
                            'service_level': 'standard',
                            'per_word_rate': 0.16
                        }]
                    ),
                    'status': 200,
                },
                {
                    'method': responses.POST,
                    'url': transcripts.THREE_PLAY_ORDER_TRANSLATION_URL.format(file_id=u'112233'),
                    'body': '1s2d3f4',
                    'status': 400
                }
            ],
            {
                'method': 'error',
                'args': (
                    '[3PlayMedia Callback] An error occurred during translation, target language=%s, file_id=%s, '
                    'status=%s',
                    'ro',
                    '112233',
                    400,
                )
            }
        ),
        # Error on 3Play during placing order for a translation.
        (
            [
                {
                    'method': responses.GET,
                    'url': transcripts.THREE_PLAY_TRANSLATION_SERVICES_URL,
                    'body': json.dumps(
                        [{
                            'id': 30,
                            'source_language_name': 'English',
                            'source_language_iso_639_1_code': 'en',
                            'target_language_name': 'Romanian',
                            'target_language_iso_639_1_code': 'ro',
                            'service_level': 'standard',
                            'per_word_rate': 0.16
                        }]
                    ),
                    'status': 200,
                },
                {
                    'method': responses.POST,
                    'url': transcripts.THREE_PLAY_ORDER_TRANSLATION_URL.format(file_id=u'112233'),
                    'body': json.dumps({'success': False}),
                    'status': 200
                }

            ],
            {
                'method': 'error',
                'args': (
                    '[3PlayMedia Callback] Translation failed fot target language=%s, file_id=%s, response=%s',
                    'ro',
                    '112233',
                    json.dumps({'success': False}),
                )
            }
        ),
        # When translation service is not found for our language
        (
            [
                {
                    'method': responses.GET,
                    'url': transcripts.THREE_PLAY_TRANSLATION_SERVICES_URL,
                    'body': json.dumps(
                        [{
                            'id': 30,
                            'source_language_name': 'English',
                            'source_language_iso_639_1_code': 'en',
                            'target_language_name': 'German',
                            'target_language_iso_639_1_code': 'de',
                            'service_level': 'standard',
                            'per_word_rate': 0.16
                        }]
                    ),
                    'status': 200,
                }
            ],
            {
                'method': 'error',
                'args': (
                    '[3PlayMedia Callback] No translation service found for '
                    'source language "%s" target language "%s" -- process id %s',
                    'en',
                    'ro',
                    '112233',
                )
            }
        )

    )
    @unpack
    @responses.activate
    @mock_s3_deprecated
    @patch('VEDA_OS01.transcripts.LOGGER')
    def test_order_translations_exception_cases(self, mock_responses, expected_logging, mock_logger):
        """
        Tests all the error scenarios while ordering translation for a transcript in various languages.
        """
        # Setup an s3 bucket
        self.setup_s3_bucket()
        # for multi-language translations
        self.video.preferred_languages = ['en', 'ro']
        self.video.save()

        # Mocked responses
        responses.add(
            responses.GET,
            transcripts.THREE_PLAY_TRANSCRIPT_URL.format(file_id=self.file_id),
            body=TRANSCRIPT_SRT_DATA,
            content_type='text/plain; charset=utf-8',
            status=200
        )
        responses.add(responses.POST, CONFIG_DATA['val_token_url'], '{"access_token": "1234567890"}', status=200)
        responses.add(responses.POST, CONFIG_DATA['val_transcript_create_url'], status=200)
        for response in mock_responses:
            responses.add(response.pop('method'), response.pop('url'), **response)

        # Make request to callback
        response = self.invoke_3play_callback()

        # Assert the response and the logs
        self.assertEqual(response.status_code, 200)
        getattr(mock_logger, expected_logging['method']).assert_called_with(*expected_logging['args'])

        # Assert the transcript translation process
        self.assertEqual(
            TranscriptProcessMetadata.objects.get(
                process_id=self.file_id,
                provider=TranscriptProvider.THREE_PLAY,
                lang_code='ro'
            ).status,
            TranscriptStatus.FAILED,
        )

    @responses.activate
    @mock_s3_deprecated
    def test_translations_retrieval(self):
        """
        Tests translations retrieval from 3PlayMedia
        """
        # Setup an S3 bucket
        connection = self.setup_s3_bucket()

        # Setup translations
        translations_lang_map = {
            'ro': '1z2x3c',
            'da': '1q2w3e',
        }
        self.setup_translations_prereqs(
            file_id=self.file_id,
            translation_lang_map=translations_lang_map,
            preferred_languages=['en', 'ro', 'da']
        )

        # Setup mock responses
        translation_status_mock_response = []
        for target_language, translation_id in translations_lang_map.iteritems():
            translation_status_mock_response.append({
                'id': translation_id,
                'source_language_iso_639_1_code': 'en',
                'target_language_iso_639_1_code': target_language,
                'state': 'complete'
            })

            responses.add(
                responses.GET,
                transcripts.THREE_PLAY_TRANSLATION_DOWNLOAD_URL.format(
                    file_id=self.file_id, translation_id=translation_id
                ),
                body=TRANSCRIPT_SRT_DATA,
                content_type='text/plain; charset=utf-8',
                status=200,
            )
            # edx-val mocked responses
            responses.add(responses.POST, CONFIG_DATA['val_token_url'], '{"access_token": "1234567890"}', status=200)
            responses.add(responses.POST, CONFIG_DATA['val_transcript_create_url'], status=200)

        responses.add(responses.PATCH, CONFIG_DATA['val_video_transcript_status_url'], status=200)
        responses.add(
            responses.GET,
            transcripts.THREE_PLAY_TRANSLATIONS_METADATA_URL.format(file_id=self.file_id),
            json.dumps(translation_status_mock_response),
            status=200
        )

        # Call to retrieve translations
        transcripts.retrieve_three_play_translations()

        # Total HTTP requests, 1 for retrieving translations metadata, 3 for first translation and
        # 3 for second translation and 1 for updating video status.
        self.assertEqual(len(responses.calls), 8)

        # Assert that the first request was made for getting translations metadata from 3Play Media.
        expected_video_status_update_request = {
            'url': utils.build_url(
                transcripts.THREE_PLAY_TRANSLATIONS_METADATA_URL.format(file_id=self.file_id),
                apikey=self.transcript_prefs.api_key
            )
        }
        self.assert_request(
            responses.calls[0].request,
            expected_video_status_update_request,
            decode_func=json.loads,
        )
        position = 1
        for lang_code, translation_id in translations_lang_map.iteritems():
            expected_requests = [
                # request - 1
                {
                    'url': utils.build_url(transcripts.THREE_PLAY_TRANSLATION_DOWNLOAD_URL.format(
                        file_id=self.file_id, translation_id=translation_id
                    ), apikey=self.transcript_prefs.api_key)
                },
                # request - 2
                {
                    'url': CONFIG_DATA['val_token_url'],
                    'body': {
                        'grant_type': ['password'],
                        'client_id': [CONFIG_DATA['val_client_id']],
                        'client_secret': [CONFIG_DATA['val_secret_key']],
                        'username': [CONFIG_DATA['val_username']],
                        'password': [CONFIG_DATA['val_password']],
                    },
                    'decode_func': urlparse.parse_qs,
                },
                # request - 3
                {
                    'url': CONFIG_DATA['val_transcript_create_url'],
                    'body': {
                        'file_format': transcripts.TRANSCRIPT_SJSON,
                        'video_id': self.video.studio_id,
                        'language_code': lang_code,
                        'name': '{directory}{uuid}.sjson'.format(
                            directory=CONFIG_DATA['aws_video_transcripts_prefix'], uuid=self.uuid_hex
                        ),
                        'provider': TranscriptProvider.THREE_PLAY
                    },
                    'headers': {
                        'Authorization': 'Bearer 1234567890',
                        'content-type': 'application/json'
                    },
                    'decode_func': json.loads,
                }
            ]
            for expected_request in expected_requests:
                self.assert_request(
                    responses.calls[position].request,
                    expected_request,
                    expected_request.pop('decode_func', None),
                )
                position += 1

            # Asserts the transcript sjson data uploaded to s3
            self.assert_uploaded_transcript_on_s3(connection=connection)

            # Asserts the Process metadata
            self.assertEqual(
                TranscriptProcessMetadata.objects.get(
                    provider=TranscriptProvider.THREE_PLAY,
                    process_id=self.file_id,
                    lang_code=lang_code,
                    translation_id=translation_id,
                ).status,
                TranscriptStatus.READY,
            )

        # Assert that the final request was made for updating video status to `ready`
        # upon receiving all the translations
        expected_video_status_update_request = {
            'url': CONFIG_DATA['val_video_transcript_status_url'],
            'body': {
                'status': utils.ValTranscriptStatus.TRANSCRIPT_READY,
                'edx_video_id': self.video.studio_id
            },
            'headers': {
                'Authorization': 'Bearer 1234567890',
                'content-type': 'application/json'
            }
        }
        self.assert_request(
            responses.calls[position].request,
            expected_video_status_update_request,
            decode_func=json.loads,
        )

        # Asserts edx-video-pipeline's video status
        video = Video.objects.get(studio_id=self.video.studio_id)
        self.assertEqual(video.transcript_status, TranscriptStatus.READY)

    @data(
        # not-an-ok response on translation status fetch request.
        (
            [
                {
                    'method': responses.GET,
                    'url': transcripts.THREE_PLAY_TRANSLATIONS_METADATA_URL.format(file_id='112233'),
                    'body': 'Your request was invalid.',
                    'status': 400,
                }
            ],
            {
                'method': 'error',
                'args': (
                    '[3PlayMedia Task] Translations metadata request failed for video=%s -- process_id=%s -- status=%s',
                    VIDEO_DATA['studio_id'],
                    '112233',
                    400,
                )
            },
            TranscriptStatus.FAILED
        ),
        # 3Play Error response on fetching translations status.
        (
            [
                {
                    'method': responses.GET,
                    'url': transcripts.THREE_PLAY_TRANSLATIONS_METADATA_URL.format(file_id='112233'),
                    'body': json.dumps({'iserror': True}),
                    'status': 200,
                }
            ],
            {
                'method': 'error',
                'args': (
                    '[3PlayMedia Task] unable to get translations metadata for video=%s -- '
                    'process_id=%s -- response=%s',
                    VIDEO_DATA['studio_id'],
                    '112233',
                    json.dumps({'iserror': True}),
                )
            },
            TranscriptStatus.FAILED,
        ),
        # not-an-ok response on translation fetch request.
        (
            [
                {
                    'method': responses.GET,
                    'url': transcripts.THREE_PLAY_TRANSLATIONS_METADATA_URL.format(file_id='112233'),
                    'body': json.dumps([{
                        'id': '1q2w3e',
                        'source_language_iso_639_1_code': 'en',
                        'target_language_iso_639_1_code': 'ro',
                        'state': 'complete'
                    }]),
                    'status': 200,
                },
                {
                    'method': responses.GET,
                    'url': transcripts.THREE_PLAY_TRANSLATION_DOWNLOAD_URL.format(
                        file_id='112233', translation_id='1q2w3e'
                    ),
                    'body': 'invalid blah blah',
                    'status': 400
                }

            ],
            {
                'method': 'exception',
                'args': (
                    '[3PlayMedia Task] Translation download failed for video=%s -- lang_code=%s -- process_id=%s.',
                    VIDEO_DATA['studio_id'],
                    'ro',
                    '112233'
                )
            },
            TranscriptStatus.IN_PROGRESS
        ),
        # 3Play Error response on translation fetch request.
        (
            [
                {
                    'method': responses.GET,
                    'url': transcripts.THREE_PLAY_TRANSLATIONS_METADATA_URL.format(file_id='112233'),
                    'body': json.dumps([{
                        'id': '1q2w3e',
                        'source_language_iso_639_1_code': 'en',
                        'target_language_iso_639_1_code': 'ro',
                        'state': 'complete'
                    }]),
                    'status': 200,
                },
                {
                    'method': responses.GET,
                    'url': transcripts.THREE_PLAY_TRANSLATION_DOWNLOAD_URL.format(
                        file_id='112233', translation_id='1q2w3e'
                    ),
                    'body': json.dumps({'iserror': True}),
                    'status': 200
                }

            ],
            {
                'method': 'error',
                'args': (
                    '[%s] Transcript fetch error for video=%s -- lang_code=%s -- process=%s -- response=%s',
                    '3PlayMedia Task',
                    VIDEO_DATA['studio_id'],
                    'ro',
                    '112233',
                    json.dumps({'iserror': True}),
                )
            },
            TranscriptStatus.FAILED
        ),
    )
    @unpack
    @responses.activate
    @mock_s3_deprecated
    @patch('VEDA_OS01.transcripts.LOGGER')
    def test_translations_retrieval_exceptions(self, mock_responses, expected_logging, transcript_status, mock_logger):
        """
        Tests possible error cases during translation fetch process form 3PlayMedia.
        """
        # Setup translation processes
        translation_id = '1q2w3e'
        self.setup_translations_prereqs(
            file_id=self.file_id,
            translation_lang_map={'ro': translation_id},
            preferred_languages=['en', 'ro']
        )

        for response in mock_responses:
            responses.add(response.pop('method'), response.pop('url'), **response)

        # Fetch translations
        transcripts.retrieve_three_play_translations()

        # Assert the logs
        getattr(mock_logger, expected_logging['method']).assert_called_with(*expected_logging['args'])

        # Assert the transcript translation process
        self.assertEqual(
            TranscriptProcessMetadata.objects.get(
                provider=TranscriptProvider.THREE_PLAY,
                process_id=self.file_id,
                translation_id=translation_id,
                lang_code='ro'
            ).status,
            transcript_status,
        )

    @patch('VEDA_OS01.transcripts.LOGGER')
    @patch('VEDA_OS01.transcripts.convert_srt_to_sjson', Mock(side_effect=ValueError))
    def test_translations_retrieval_uncaught_exceptions(self, mock_logger):
        """
        Test that `convert_to_sjson_and_upload_to_s3` logs and throws any uncaught exceptions
        during translation retrieval process.
        """
        with self.assertRaises(ValueError):
            transcripts.convert_to_sjson_and_upload_to_s3(
                srt_transcript='invalid SRT content}',
                edx_video_id=self.video.studio_id,
                file_id=self.file_id,
                target_language='es'
            )

        mock_logger.exception.assert_called_with(
            u'[3PlayMedia Task] translation failed for video=%s -- lang_code=%s -- process_id=%s',
            self.video.studio_id,
            self.file_id,
            'es',
        )

    @patch('VEDA_OS01.transcripts.LOGGER')
    def test_translations_retrieval_with_zero_translation_process(self, mock_logger):
        """
        Tests the translations retrieval when a video doesn't have any 'in progress' translation processes.
        """
        # Try fetching translations
        transcripts.retrieve_three_play_translations()
        # Assert the logs
        mock_logger.info.assert_called_with(
            '[3PlayMedia Task] video=%s does not have any translation process who is in progress.',
            self.video.studio_id,
        )

    @patch('VEDA_OS01.transcripts.LOGGER')
    def test_translations_retrieval_no_credentials(self, mock_logger):
        """
        Tests the the translations retrieval when 3Play Media credentials are deleted from the data model.
        """
        translation_id = '1q2w3e'
        self.setup_translations_prereqs(
            file_id=self.file_id,
            translation_lang_map={'ro': translation_id},
            preferred_languages=['en', 'ro']
        )
        # Delete transcript credentials
        TranscriptCredentials.objects.all().delete()

        # Try fetching translations
        transcripts.retrieve_three_play_translations()

        # assert the exception logs
        mock_logger.exception.assert_called_with(
            '[%s] Unable to get transcript secrets for org=%s, edx_video_id=%s, file_id=%s.',
            '3PlayMedia Task',
            self.org,
            self.video.studio_id,
            self.file_id,
        )

        # assert the translation process status
        process = TranscriptProcessMetadata.objects.get(
            provider=TranscriptProvider.THREE_PLAY,
            process_id=self.file_id,
            translation_id=translation_id,
            lang_code='ro'
        )
        self.assertEqual(process.status, TranscriptStatus.FAILED)

    @responses.activate
    @patch('VEDA_OS01.transcripts.LOGGER')
    def test_translations_retrieval_with_removed_translation_process(self, mock_logger):
        """
        Tests the translations retrieval when a tracking translation process is not there or deleted.
        """
        translation_id = '1q2w3e'
        non_existent_target_language = 'es'
        self.setup_translations_prereqs(
            file_id=self.file_id,
            translation_lang_map={'ro': translation_id},
            preferred_languages=['en', 'ro']
        )

        # We get Translations metadata for a language whose tracking process is no more in pipeline.
        responses.add(
            method=responses.GET,
            url=transcripts.THREE_PLAY_TRANSLATIONS_METADATA_URL.format(file_id='112233'),
            body=json.dumps([{
                'id': translation_id,
                'source_language_iso_639_1_code': 'en',
                'target_language_iso_639_1_code': non_existent_target_language,
                'state': 'complete'
            }]),
            status=200
        )

        # Try fetching translations
        transcripts.retrieve_three_play_translations()

        mock_logger.warning.assert_called_with(
            (u'[3PlayMedia Task] Tracking process is either not found or already complete '
             u'-- process_id=%s -- target_language=%s -- translation_id=%s.'),
            '112233',
            non_existent_target_language,
            translation_id,
        )

    @data(None, 'invalid_course_id_1, invalid_course_id_2')
    @patch('VEDA_OS01.transcripts.LOGGER')
    def test_translation_retrieval_with_invalid_course_id(self, course_runs, mock_logger):
        """
        Tests the translations retrieval when an associated course does not have course ids or
        have some invalid course ids.

        Note:
            Its insane for a course to not to have course id but we have to do as
            `Course.local_storedir` is null=True, blank=True.
        """
        self.setup_translations_prereqs(
            file_id=self.file_id,
            translation_lang_map={'ro': '1q2w3e'},
            preferred_languages=['en', 'ro']
        )

        # Make our course to not to have course ids.
        self.course.local_storedir = course_runs
        self.course.save()

        # Now, Try fetching translations
        transcripts.retrieve_three_play_translations()

        mock_logger.exception.assert_called_with(
            u'[%s] Unable to get transcript secrets for org=%s, edx_video_id=%s, file_id=%s.',
            '3PlayMedia Task',
            None,
            self.edx_video_id,
            self.file_id,
        )
