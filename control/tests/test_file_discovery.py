"""
Unit Tests for File Discovery Phase.
"""
from contextlib import contextmanager
import ddt
import json
import os
import shutil
import tempfile

from boto.s3.connection import S3Connection
from boto.s3.key import Key
from boto.exception import S3ResponseError, S3DataError
from django.test import TestCase
from mock import ANY, Mock, patch
from moto import mock_s3_deprecated
from opaque_keys.edx.keys import CourseKey

from control.veda_file_discovery import FileDiscovery
from VEDA.utils import get_config
from VEDA_OS01.models import Course, TranscriptCredentials, TranscriptProvider


CONFIG_DATA = get_config('test_config.yaml')
TEST_FILES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'test_files')

# Default S3 metadata
S3_METADATA = {
    'course_video_upload_token': 'xxx',
    'client_video_id': 'OVTESTFILE_01.mp4',
    'course_key': 'course-v1:MAx+123+test_run',
    'transcript_preferences': json.dumps({})
}

# Default course data
COURSE_DATA = {
    'course_name': 'MAx 123',
    'institution': 'MAx',
    'edx_classid': '123',
    'local_storedir': ''
}


@contextmanager
def temporary_directory():
    """
    Context manager for tempfile.mkdtemp() so it's usable with "with" statement.
    """
    name = tempfile.mkdtemp()
    yield name
    shutil.rmtree(name)


@ddt.ddt
@mock_s3_deprecated
@patch('control.veda_file_discovery.get_config', Mock(return_value=CONFIG_DATA))
class TestFileDiscovery(TestCase):
    """
    Tests for file discovery phase.
    """
    def setUp(self):
        self.file_name = u'OVTESTFILE_01.mp4'
        self.video_file_path = os.path.join(TEST_FILES_DIR, self.file_name)

        # Create s3 bucket -- all this is happening in moto virtual environment
        connection = S3Connection()
        connection.create_bucket(CONFIG_DATA['edx_s3_ingest_bucket'])

    def upload_video_with_metadata(self, **metadata):
        """
        Sets the metadata on an S3 video key.
        """
        # Upload the video file to ingest bucket
        connection = S3Connection()
        self.ingest_bucket = connection.get_bucket(CONFIG_DATA['edx_s3_ingest_bucket'])

        key_name = os.path.join(CONFIG_DATA['edx_s3_ingest_prefix'], self.file_name)
        self.video_key = Key(self.ingest_bucket, key_name)
        for metadata_name, value in dict(S3_METADATA, **metadata).iteritems():
            if value is not None:
                self.video_key.set_metadata(metadata_name, value)

        self.video_key.set_contents_from_filename(self.video_file_path)

    def setup_course(self, **course_data):
        """
        Sets up a course.

        Arguments:
            course_data(dict): A dict containing the course properties.
        """
        return Course.objects.create(**dict(COURSE_DATA, **course_data))

    def assert_video_location(self, filename, expected_directory):
        """
        Asserts that video file is in the expected directory.

        Arguments:
            filename: Name of the file.
            expected_directory: A prefix in which the file with filename is expected.
        """
        videos = list(self.ingest_bucket.list(expected_directory, '/'))
        self.assertEqual(len(videos), 1)
        self.assertEqual(os.path.basename(videos[0].name), filename)

    @ddt.data(
        (
            'course-v1:MAx+123+test_run',
            json.dumps({'provider': TranscriptProvider.THREE_PLAY}),
            {'provider': TranscriptProvider.THREE_PLAY}
        ),
        (
            'invalid_course_key',
            json.dumps({'provider': TranscriptProvider.THREE_PLAY}),
            None
        ),
        (
            'course-v1:MAx+123+test_run',
            'invalid_json_data',
            None
        ),
    )
    @ddt.unpack
    def test_parse_transcript_preferences(self, course_id, transcript_preferences, expected_preferences):
        """
        Tests that 'FileDiscovery.parse_transcript_preferences' works as expected.
        """
        # create test credentials
        TranscriptCredentials.objects.create(
            org='MAx',
            provider=TranscriptProvider.THREE_PLAY,
            api_key='test-api-key',
            api_secret='test-api-secret'
        )
        file_discovery = FileDiscovery()
        actual_preferences = file_discovery.parse_transcript_preferences(course_id, transcript_preferences)
        # Assert the transcript preferences.
        assert actual_preferences == expected_preferences

    @patch('control.veda_file_discovery.VALAPICall.call')
    def test_reject_file_and_update_val(self, mock_val_api):
        """
        Tests that 'FileDiscovery.reject_file_and_update_val' works as expected.
        """
        self.upload_video_with_metadata()
        # instantiate file discovery instance with the ingest bucket.
        file_discovery_instance = FileDiscovery()
        file_discovery_instance.bucket = self.ingest_bucket

        # rejecting a key will move it to 'prod-edx/rejected/ingest/' directory in the bucket.
        file_discovery_instance.reject_file_and_update_val(self.video_key, ANY, ANY, ANY)

        self.assertTrue(mock_val_api.called)
        # assert that video file is no more in '/ingest' directory.
        ingested_videos = list(self.ingest_bucket.list(CONFIG_DATA['edx_s3_ingest_prefix'], '/'))
        self.assertEqual(ingested_videos, [])

        # assert that video file is now among rejected videos.
        self.assert_video_location(self.file_name, CONFIG_DATA['edx_s3_rejected_prefix'])

    @patch('control.veda_file_discovery.FileDiscovery.validate_metadata_and_feed_to_ingest')
    def test_discover_studio_ingested_videos(self, mock_validate_and_feed_to_ingest):
        """
        Tests that 'FileDiscovery.discover_studio_ingested_videos' works as expected.
        """
        self.upload_video_with_metadata()
        with temporary_directory() as node_work_directory:
            file_discovery_instance = FileDiscovery(node_work_directory=node_work_directory)
            file_discovery_instance.discover_studio_ingested_videos()
            self.assertTrue(mock_validate_and_feed_to_ingest.called)

    @ddt.data(
        ('veda/working', '[File Ingest] S3 Ingest Connection Failure'),
        (None, '[File Ingest] No Working Node directory')
    )
    @ddt.unpack
    @patch('control.veda_file_discovery.ErrorObject.print_error')
    @patch('boto.s3.connection.S3Connection')
    def test_discover_studio_ingested_video_exceptions(self, work_dir, error_message, mocked_s3_conn, mock_error):
        """
        Tests 'FileDiscovery.discover_studio_ingested_videos' exception cases.
        """
        mocked_s3_conn.side_effect = S3ResponseError('Error', 'Timeout')
        file_discovery_instance = FileDiscovery(node_work_directory=work_dir)
        file_discovery_instance.discover_studio_ingested_videos()
        mock_error.assert_called_with(message=error_message)

    @ddt.data(
        (None, 'invalid_course_key'),
        ('non-existent-hex', None)
    )
    @ddt.unpack
    @patch('control.veda_file_discovery.VALAPICall.call')
    def test_validate_metadata_and_feed_to_ingest_invalid_course(self, course_hex, course_key, mock_val_api):
        """
        Tests 'validate_metadata_and_feed_to_ingest' with non-existent course hex and invalid
        course key, this won't create a course.
        """
        self.upload_video_with_metadata(course_video_upload_token=course_hex, course_key=course_key)
        with temporary_directory() as node_work_directory:
            file_discovery_instance = FileDiscovery(node_work_directory=node_work_directory)
            file_discovery_instance.discover_studio_ingested_videos()

        # assert that video file now among rejected videos.
        self.assert_video_location(self.file_name, CONFIG_DATA['edx_s3_rejected_prefix'])
        self.assertTrue(mock_val_api.called)

    @ddt.data(
        'course-v1:MAx+123+test_run',
        'course-v1:new_org+new_number+new_run'
    )
    @patch('control.veda_file_discovery.VedaIngest', Mock(complete=True))
    @patch('control.veda_file_discovery.FileDiscovery.parse_transcript_preferences', Mock(return_value={}))
    def test_validate_metadata_and_feed_to_ingest_happy_flow(self, course_id):
        """
        Tests 'validate_metadata_and_feed_to_ingest' once with existing course and then with valid
        course key, while the course_hex is not set.
        """
        self.setup_course()
        self.upload_video_with_metadata(course_video_upload_token=None, course_key=course_id)
        with temporary_directory() as node_work_directory:
            file_discovery_instance = FileDiscovery(node_work_directory=node_work_directory)
            file_discovery_instance.discover_studio_ingested_videos()

            # Assert the course in the database.
            course_key = CourseKey.from_string(course_id)
            course = Course.objects.get(institution=course_key.org, edx_classid=course_key.course)
            self.assertEqual(course.course_name, ' '.join([course_key.org, course_key.course]))
            self.assertEqual(course.local_storedir, course_id)

        # assert that video file has been ingested successfully.
        self.assert_video_location(self.file_name, CONFIG_DATA['edx_s3_processed_prefix'])

    @patch('boto.s3.key.Key.get_contents_to_filename', Mock(side_effect=S3DataError('Unable to download.')))
    def test_validate_metadata_and_feed_to_ingest_with_download_failure(self):
        """
        Tests 'validate_metadata_and_feed_to_ingest' with video download failure from s3 to working directory.
        """
        self.setup_course()
        self.upload_video_with_metadata(course_video_upload_token=None)
        with temporary_directory() as node_work_directory:
            file_discovery_instance = FileDiscovery(node_work_directory=node_work_directory)
            file_discovery_instance.discover_studio_ingested_videos()

        # assert that video file now among rejected videos.
        self.assert_video_location(self.file_name, CONFIG_DATA['edx_s3_rejected_prefix'])
