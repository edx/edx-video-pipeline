"""
multi-point videofile discovery
Currently:
    Amazon S3 (studio-ingest as well as about/marketing
        video ingest
        )
    Local (watchfolder w/o edit priv.)

"""

import json
import logging
import os.path

import boto
import boto.s3
from boto.exception import NoAuthHandlerFound, S3DataError, S3ResponseError
from opaque_keys import InvalidKeyError
from opaque_keys.edx.keys import CourseKey

from control_env import *
from VEDA.utils import extract_course_org, get_config
from veda_file_ingest import VedaIngest, VideoProto
from VEDA_OS01.models import TranscriptCredentials
from veda_val import VALAPICall

try:
    boto.config.add_section('Boto')
except:
    pass
boto.config.set('Boto', 'http_socket_timeout', '100')

logging.basicConfig(level=logging.INFO)
logging.getLogger("requests").setLevel(logging.WARNING)
logging.getLogger("boto").setLevel(logging.ERROR)
LOGGER = logging.getLogger(__name__)


class FileDiscovery(object):

    def __init__(self, **kwargs):
        self.video_info = {}
        self.auth_dict = get_config()
        self.bucket = None
        self.node_work_directory = kwargs.get('node_work_directory', WORK_DIRECTORY)

        # In stage, a course could possibly not exist in the local database
        # but remain referenced by edx-platform.
        # If the course doesn't exist but a course ID and hex is supplied,
        # create the course anyway.
        self.create_course_override = self.auth_dict['environment'] == "stage"

    def about_video_validate(self, meta, key):
        abvid_serial = meta.name.split('/')[1]
        upload_query = VedaUpload.objects.filter(
            video_serial=meta.name.split('/')[1]
        )
        if len(upload_query) == 0:
            # Non serialized upload - reject
            return

        if upload_query[0].upload_filename is not None:
            file_extension = upload_query[0].upload_filename.split('.')[-1]
        else:
            upload_query[0].upload_filename = 'null_file_name.mp4'
            file_extension = 'mp4'

        if len(file_extension) > 4:
            file_extension = ''

        meta.get_contents_to_filename(
            os.path.join(
                self.node_work_directory,
                upload_query[0].upload_filename
            )
        )

        course_query = Course.objects.get(institution='EDX', edx_classid='ABVID')

        # Trigger Ingest Process
        V = VideoProto(
            abvid_serial=abvid_serial,
            client_title=upload_query[0].upload_filename.replace('.' + file_extension, ''),
            file_extension=file_extension,
        )

        I = VedaIngest(
            course_object=course_query,
            video_proto=V,
            node_work_directory=self.node_work_directory
        )
        I.insert()

        """
        Move Key out of 'upload' folder
        """
        new_key = '/'.join(('process', meta.name.split('/')[1]))
        key.copy(self.bucket, new_key)
        key.delete()

        reset_queries()

    def move_video(self, key, destination_dir):
        """
        Moves an S3 video key to destination directory within the same bucket.

        Arguments:
            key: An S3 file key.
            destination_dir: target directory where the key will be moved eventually.
        """
        new_key_name = os.path.join(destination_dir, os.path.basename(key.name))
        key.copy(self.bucket, new_key_name)
        key.delete()

    def reject_file_and_update_val(self, key, s3_filename, client_title, course_id):
        """
        Moves a video file to rejected videos, update edx-val to 'invalid_token'.

        Arguments:
            key: An S3 key to be moved to /rejected
            s3_filename: Name of the file
            client_title: client title from Key's S3 metadata
            course_id: course run identifier
        """
        video_proto = VideoProto(
            s3_filename=s3_filename,
            client_title=client_title,
            file_extension='',
            platform_course_url=course_id,
            video_orig_duration=0.0
        )
        # Update val status to 'invalid_token'
        VALAPICall(video_proto=video_proto, val_status=u'invalid_token').call()
        # Move the video file to 'edx-prod/rejected' directory.
        self.move_video(key, destination_dir=self.auth_dict['edx_s3_rejected_prefix'])

    def get_or_create_course(self, course_id, course_hex=None):
        """
        Retrieves a course associated with course_hex, course_id or a creates new one.

        Arguments:
            course_id: course id identifying a course run
            course_hex: studio_hex identifying course runs

        Details:
         - if course_hex is there, try getting course with course_hex.
         - otherwise try making use of course_id to get the associated course
           and if no course is associated with the course_id, try creating
           a new course with course_name, institution, edx_classid and
           local_storedir.

        """
        if not course_hex:
            try:
                course_key = CourseKey.from_string(course_id)
            except InvalidKeyError:
                return

            course = Course.objects.filter(institution=course_key.org, edx_classid=course_key.course).first()
            if course:
                course_runs = course.course_runs
                if course_id not in course_runs:
                    course_runs.append(course_id)
                    course.local_storedir = ','.join(course_runs)
                    course.save()
            else:
                course = self._create_course(course_key, course_id)
        else:
            try:
                course = Course.objects.get(studio_hex=course_hex)
            except Course.DoesNotExist:
                if self.create_course_override:
                    try:
                        course_key = CourseKey.from_string(course_id)
                    except InvalidKeyError:
                        return

                    course = self._create_course(course_key, course_id, course_hex)
                else:
                    return

        return course

    def _create_course(self, course_key, course_id, studio_hex=None):
        """
        Creates a course with the specified parameters.
        If another class needs to create a course, use get_or_create_course
        instead of this method.

        Arguments:
            -  course_key
            -  course_id
            -  studio_hex
        """
        course_name = '{org} {number}'.format(org=course_key.org, number=course_key.course)
        course = Course.objects.create(
            course_name=course_name,
            institution=course_key.org,
            edx_classid=course_key.course,
            local_storedir=course_id,
            yt_proc=False
        )

        if studio_hex:
            setattr(course, 'studio_hex', studio_hex)

        return course

    def download_video_to_working_directory(self, key, file_name):
        """
        Downloads the video to working directory from S3 and
        returns whether its successfully downloaded or not.

        Arguments:
            key: An S3 key whose content is going to be downloaded
            file_name: Name of the file when its in working directory
        """
        file_ingested = False
        try:
            key.get_contents_to_filename(os.path.join(self.node_work_directory, file_name))
            file_ingested = True
        except S3DataError:
            LOGGER.error('[DISCOVERY] Error downloading the file into node working directory.')
        return file_ingested

    def parse_transcript_preferences(self, course_id, transcript_preferences):
        """
        Parses and validates transcript preferences.

        Arguments:
            course_id: course id identifying a course run.
            transcript_preferences: A serialized dict containing third party transcript preferences.
        """
        try:
            transcript_preferences = json.loads(transcript_preferences)
            TranscriptCredentials.objects.get(
                org=extract_course_org(course_id),
                provider=transcript_preferences.get('provider')
            )
        except (TypeError, TranscriptCredentials.DoesNotExist):
            # when the preferences are not set OR these are set to some data in invalid format OR these don't
            # have associated 3rd party transcription provider API keys.
            transcript_preferences = None
        except ValueError:
            LOGGER.error('[DISCOVERY] Invalid transcripts preferences=%s', transcript_preferences)
            transcript_preferences = None

        return transcript_preferences

    def validate_metadata_and_feed_to_ingest(self, video_s3_key):
        """
        Validates the video key and feed it to ingestion phase.

        Arguments:
            video_s3_key: An S3 Key associated with a (to be ingested)video file.

        Process/Steps:
            1 - Get or create an associated course for a video.
            2 - Download video to node working directory from S3.
            3 - Check if this video has valid 3rd Party transcript provider along with the preferences.
            4 - Set up an ingest instance and insert video to ingestion phase.
            5 - On completing ingestion, mark the video file as processed.

            Note:
                Failure at any discovery point will cause video file to be marked as rejected.
        """
        client_title = video_s3_key.get_metadata('client_video_id')
        course_hex = video_s3_key.get_metadata('course_video_upload_token')
        course_id = video_s3_key.get_metadata('course_key')
        transcript_preferences = video_s3_key.get_metadata('transcript_preferences')
        filename = os.path.basename(video_s3_key.name)

        # Try getting course based on the S3 metadata set on the video file.
        course = self.get_or_create_course(course_id, course_hex=course_hex)
        if course:
            # Download video file from S3 into node working directory.
            file_extension = os.path.splitext(client_title)[1][1:]
            file_downloaded = self.download_video_to_working_directory(video_s3_key, filename)
            if not file_downloaded:
                # S3 Bucket ingest failed, move the file rejected directory.
                self.move_video(video_s3_key, destination_dir=self.auth_dict['edx_s3_rejected_prefix'])
                return

            # Prepare to ingest.
            video_metadata = dict(
                s3_filename=filename,
                client_title=client_title,
                file_extension=file_extension,
                platform_course_url=course_id,
            )
            # Check if this video also having valid 3rd party transcription preferences.
            transcript_preferences = self.parse_transcript_preferences(course_id, transcript_preferences)
            if transcript_preferences is not None:
                video_metadata.update({
                    'process_transcription': True,
                    'provider': transcript_preferences.get('provider'),
                    'three_play_turnaround': transcript_preferences.get('three_play_turnaround'),
                    'cielo24_turnaround': transcript_preferences.get('cielo24_turnaround'),
                    'cielo24_fidelity': transcript_preferences.get('cielo24_fidelity'),
                    'preferred_languages': transcript_preferences.get('preferred_languages'),
                    'source_language': transcript_preferences.get('video_source_language'),
                })

            ingest = VedaIngest(
                course_object=course,
                video_proto=VideoProto(**video_metadata),
                node_work_directory=self.node_work_directory
            )
            ingest.insert()

            if ingest.complete:
                # Move the video file into 'prod-edx/processed' or 'stage-edx/processed
                # directory, if ingestion is complete.
                self.move_video(video_s3_key, destination_dir=self.auth_dict['edx_s3_processed_prefix'])
        else:
            # Reject the video file and update val status to 'invalid_token'
            self.reject_file_and_update_val(video_s3_key, filename, client_title, course_id)
