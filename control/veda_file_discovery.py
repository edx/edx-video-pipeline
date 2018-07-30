"""
multi-point videofile discovery
Currently:
    Amazon S3 (about/marketing)
    Local (watchfolder w/o edit priv.)

Other utils in this file
(feed_to_ingest and
insert_video_to_database) are used by the
HTTP endpoint called by the SNS resource
to ingest Studio-uploaded videos.
"""

import logging
import os.path
import threading

import boto
import boto.s3
from boto.exception import NoAuthHandlerFound, S3DataError, S3ResponseError

from celeryapp_ingest import ingest
from veda_utils import move_video_within_s3
from control_env import *
from VEDA.utils import get_config
from veda_file_ingest import VedaIngest, VideoProto
from VEDA_OS01.utils import get_or_create_course
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

auth_dict = get_config()


class FileDiscovery(object):

    def __init__(self, **kwargs):
        self.video_info = {}
        self.bucket = None
        self.node_work_directory = kwargs.get('node_work_directory', WORK_DIRECTORY)

    def about_video_ingest(self):
        """
        Crawl VEDA Upload bucket
        """
        if self.node_work_directory is None:
            LOGGER.error('[DISCOVERY] No Workdir')
            return
        try:
            conn = boto.connect_s3()
        except NoAuthHandlerFound:
            LOGGER.error('[DISCOVERY] BOTO Auth Handler')
            return
        try:
            self.bucket = conn.get_bucket(auth_dict['veda_s3_upload_bucket'])
        except S3ResponseError:
            return None
        for key in self.bucket.list('upload/', '/'):
            meta = self.bucket.get_key(key.name)
            if meta.name != 'upload/':
                self.about_video_validate(
                    meta=meta,
                    key=key
                )

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
        I.insert_video_to_ingestion_phase()

        """
        Move Key out of 'upload' folder
        """
        new_key = '/'.join(('process', meta.name.split('/')[1]))
        key.copy(self.bucket, new_key)
        key.delete()

        reset_queries()


def feed_to_ingest(s3_key_id, bucket):
    """
    Validates the video key and feed it to ingestion phase.
    Used by the HTTP endpoint '/api/ingest_from_s3' to process SNS notifications from Amazon.

    Arguments:
        s3_key_id: An S3 Key ID associated with a (to be ingested) video file.
        bucket: The bucket that the key is stored in.

    Process/Steps:
        1 - Get or create an associated course for a video.
        2 - Insert the video, with bare-bones information, into the database.
        3 - Queue a celery task to ingest.

        Note:
            Failure at any discovery point will cause video file to be marked as rejected.
    """
    video_s3_key = bucket.get_key(s3_key_id)

    if video_s3_key is None:
        LOGGER.error(
            '[INGEST] Video key {vd_key} supplied in notification but not found in the s3 bucket.'
            'Ingest will not be retried'.format(
                vd_key=video_s3_key
            ))
        return

    course_hex = video_s3_key.get_metadata('course_video_upload_token')
    course_id = video_s3_key.get_metadata('course_key')
    filename = os.path.basename(video_s3_key.name)
    client_title = video_s3_key.get_metadata('client_video_id')

    # Try getting course based on the S3 metadata set on the video file.
    course = get_or_create_course(course_id,course_hex)
    if course:
        studio_upload_id = s3_key_id.lstrip(auth_dict['edx_s3_ingest_prefix'])
        video_edx_id = _insert_video_to_database(studio_upload_id, course)

        # Download video file from S3 into ingest node working
        # directory and complete ingest.
        ingest.apply_async(
            (s3_key_id, course.id, video_edx_id),
            queue=auth_dict['celery_ingest_queue'].strip(),
            connect_timeout=3
        )
    else:
        # Reject the video file and update val status to 'invalid_token'
        _reject_file_and_update_val(bucket, video_s3_key, filename, client_title, course_id)


def _insert_video_to_database(studio_upload_id, course):
    """
    Upon receiving an SNS notification from Amazon, insert the video with basic information
    into the VEDA database, with a status that denotes that the video has been received
    from SNS.
    This video object is later edited by ingest with more information.
    """

    def _generate_veda_id():
        """
        Generate veda_id / update course record with new "last video ID"
        * Note: The lock is necessary! Otherwise, multiple ingest processes
            will end up saving two unrelated videos under the same ID.
        * Note: defensive against the possibility of later passing in an ID
        """
        with threading.RLock():
            last_video_id = course.last_vid_number + 100
            veda_id = course.institution
            veda_id += course.edx_classid
            veda_id += course.semesterid
            veda_id += "-V" + str(last_video_id).zfill(6)

            course.last_vid_number = last_video_id
            course.save()
        return veda_id

    video = Video(inst_class=course)

    video.edx_id = _generate_veda_id()
    video.studio_id = studio_upload_id
    video.video_trans_status = 'SNS Notification'
    video.save()

    return video.edx_id


def _reject_file_and_update_val(bucket, key, s3_filename, client_title, course_id):
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
    move_video_within_s3(bucket, key, destination_dir=auth_dict['edx_s3_rejected_prefix'])
