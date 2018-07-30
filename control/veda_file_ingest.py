"""
File ingest/insert/job triggering
Called in two places:
1. After an SNS notification from the HTTP endpoint '/api/ingest_from_s3'
2. After file discovery for 'about' videos
"""
import datetime
import logging
import subprocess

from boto.exception import NoAuthHandlerFound, S3DataError, S3ResponseError
from django.db.utils import DatabaseError

from control_env import *
from control.veda_utils import connect_to_boto_and_get_bucket
from VEDA.utils import get_config, decode_to_ascii
from veda_heal import VedaHeal
from veda_hotstore import Hotstore
from veda_utils import Report, move_video_within_s3
from veda_val import VALAPICall
from veda_video_validation import validate_video

LOGGER = logging.getLogger(__name__)

'''
V = VideoProto(
    s3_filename=edx_filename,
    client_title=client_title,
    file_extension=file_extension,
    platform_course_url=platform_course_url
    )

I = VedaIngest(
    course_id=course_query[0],
    video_proto=V
    )
I.insert()

if I.complete is False:
    return None
'''


class VideoProto(object):

    def __init__(self, **kwargs):
        self.s3_filename = kwargs.get('s3_filename', None)
        self.client_title = kwargs.get('client_title', None)
        self.file_extension = kwargs.get('file_extension', None)
        self.platform_course_url = kwargs.get('platform_course_url', None)
        self.abvid_serial = kwargs.get('abvid_serial', None)
        self.veda_id = kwargs.get('veda_id', None)

        # Transcription Process related Attributes
        self.process_transcription = kwargs.get('process_transcription', False)
        self.provider = kwargs.get('provider', None)
        self.three_play_turnaround = kwargs.get('three_play_turnaround', None)
        self.cielo24_turnaround = kwargs.get('cielo24_turnaround', None)
        self.cielo24_fidelity = kwargs.get('cielo24_fidelity', None)
        self.preferred_languages = kwargs.get('preferred_languages', [])
        self.source_language = kwargs.get('source_language', None)

        # Determined Videofile Attributes
        self.valid = False
        self.filesize = 0
        self.duration = 0
        self.bitrate = None
        self.resolution = None


class VedaIngest(object):

    def __init__(self, course_object, video_proto, **kwargs):
        self.course_object = course_object
        self.video_proto = video_proto
        self.auth_dict = get_config()
        self.node_work_directory = kwargs.get('node_work_directory', WORK_DIRECTORY)
        self.full_filename = kwargs.get('full_filename', None)
        self.complete = False
        self.archived = False
        self.s3_key_id = kwargs.get('s3_key_id', None)
        self.bucket = connect_to_boto_and_get_bucket(CONFIG['edx_s3_ingest_bucket'])

        if self.s3_key_id:
            self.studio_upload_id = self.s3_key_id.lstrip(CONFIG['edx_s3_ingest_prefix'])
            self.s3_key = self.bucket.get_key(self.s3_key_id)

    def ingest_from_s3(self):
        """
        Ingests a video from S3. Steps:
        1 - Download video to node working directory from S3.
        2 - Set up an ingest instance and insert video to ingestion phase.
        3 - Move the video to 'processed' directory in s3.
        """
        filename = self.video_proto.s3_filename
        file_downloaded = self._download_video_to_working_directory(filename)

        if not file_downloaded:
            move_video_within_s3(
                bucket=self.bucket,
                video_key=self.s3_key,
                destination_dir=self.auth_dict['edx_s3_rejected_prefix']
            )
        else:
            self.insert_video_to_ingestion_phase()

            if self.complete:
                move_video_within_s3(
                    bucket=self.bucket,
                    video_key=self.s3_key,
                    destination_dir=self.auth_dict['edx_s3_processed_prefix']
                )

    def insert_video_to_ingestion_phase(self):
        self.insert_video_to_database()
        self.val_insert()
        self.rename()
        self.archived = self.upload_to_hotstore()
        LOGGER.info('[INGEST] {studio_id} | {video_id} : Video in hot store'.format(
            studio_id=self.video_proto.s3_filename,
            video_id=self.video_proto.veda_id
        ))
        if self.video_proto.valid is False:
            self.abvid_report()
            self.complete = True
            if self.archived:
                os.remove(self.full_filename)
            return

        LOGGER.info('[INGEST] {studio_id} | {video_id} : Ingested {datetime}'.format(
            studio_id=self.video_proto.s3_filename,
            video_id=self.video_proto.veda_id,
            datetime=str(datetime.datetime.utcnow()))
        )

        self._queue_encode_job()
        Course.objects.filter(
            pk=self.course_object.pk
        ).update(
            previous_statechange=datetime.datetime.utcnow().replace(tzinfo=utc)
        )
        if self.archived:
            os.remove(self.full_filename)
        self.complete = True

    def insert_video_to_database(self):
        """
        Start DB Inserts, Get Basic File name information
        """
        if self.video_proto.s3_filename:
            self.full_filename = '/'.join((
                self.node_work_directory,
                self.video_proto.s3_filename
            ))
        if self.video_proto.abvid_serial:
            self.full_filename = '/'.join((
                self.node_work_directory,
                self.video_proto.client_title
            ))
            if len(self.video_proto.file_extension) > 2:
                self.full_filename += "." + self.video_proto.file_extension

        if not self.full_filename:
            self.full_filename = '/'.join((
                self.node_work_directory,
                self.video_proto.client_title
            ))

        if not os.path.exists(self.full_filename):
            LOGGER.exception(
                '[INGEST] {studio_id} | {video_id} : Local file not found'.format(
                    studio_id=self.video_proto.s3_filename,
                    video_id=self.video_proto.veda_id
                )
            )
            return

        valid_video = self._validate_file()
        if not valid_video:
            return

        valid_video.update_video_with_video_proto_data(self.video_proto)
        self._mark_video_ready_for_task_fire(valid_video)

        try:
            valid_video.save()
        except DatabaseError:
            decoded_string = decode_to_ascii(self.video_proto.client_title)
            valid_video.client_title = decoded_string
            valid_video.save()
        except Exception:
            LOGGER.exception('[INGEST] {studio_id} | {video_id} : Video catalog failed.'.format(
                studio_id=self.video_proto.s3_filename,
                video_id=self.video_proto.veda_id
            ))
            raise
        LOGGER.info('[INGEST] {studio_id} | {video_id} : Video record cataloged'.format(
            studio_id=self.video_proto.s3_filename,
            video_id=self.video_proto.veda_id
        ))

    def val_insert(self):
        if self.video_proto.abvid_serial:
            return None

        if self.video_proto.valid is False:
            val_status = 'file_corrupt'
        else:
            val_status = 'ingest'

        val_call = VALAPICall(
            video_proto=self.video_proto,
            val_status=val_status,
            platform_course_url=""  # Empty record for initial status update
        )
        val_call.call()

    def abvid_report(self):
        if self.video_proto.abvid_serial is None:
            return None

        email_report = Report(
            status="File Corrupt on Ingest",
            upload_serial=self.video_proto.abvid_serial,
            youtube_id=''
        )
        email_report.upload_status()
        LOGGER.info('[INGEST] {video_id} : About video reported'.format(
            video_id=self.video_proto.veda_id
        ))
        self.complete = True

    def rename(self):
        """
        Rename to VEDA ID
        """
        if self.video_proto.veda_id is None:
            self.video_proto.valid = False
            return

        veda_filename = self.video_proto.veda_id
        if self.video_proto.file_extension:
            veda_filename += '.{ext}'.format(ext=self.video_proto.file_extension)
        os.rename(
            self.full_filename, os.path.join(
                self.node_work_directory,
                veda_filename
            )
        )
        self.full_filename = os.path.join(self.node_work_directory, veda_filename)
        os.system('chmod ugo+rwx ' + self.full_filename)
        return

    def upload_to_hotstore(self):
        """
        Ingest File Backup / Archive Policy
        """
        H1 = Hotstore(
            video_proto=self.video_proto,
            upload_filepath=self.full_filename
        )
        return H1.upload()

    def _queue_encode_job(self):
        encode_instance = VedaHeal(
            video_query=Video.objects.filter(
                edx_id=self.video_proto.veda_id.strip()
            ),
            val_status='transcode_queue'
        )
        encode_instance.send_encodes()

    def _gather_metadata(self):
        """
        use st filesize for filesize
        Use "ffprobe" for other metadata
        """
        self.video_proto.filesize = os.stat(self.full_filename).st_size

        ff_command = ' '.join((
            FFPROBE,
            "\'" + self.full_filename + "\'"
        ))
        p = subprocess.Popen(ff_command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True)

        for line in iter(p.stdout.readline, b''):
            if "Duration: " in line:

                self.video_proto.duration = line.split(',')[0].split(' ')[-1]
                try:
                    bitrate = line.split(',')[2].split(' :')[-1].strip()
                    self.video_proto.bitrate = bitrate.replace('bitrate: ', '')
                except:
                    pass

            elif "Stream #" in line:
                if " Video: " in line:
                    vid_breakout = line.split(',')
                    vid_reso_break = vid_breakout[2].strip().split(' ')
                    for v in vid_reso_break:
                        if "x" in v:
                            self.video_proto.resolution = v.strip()
                    if self.video_proto.resolution is None:
                        self.video_proto.resolution = vid_breakout[3].strip()
                    if ')' in self.video_proto.resolution.strip():
                        if ')' not in vid_breakout[4].strip():
                            self.video_proto.resolution = vid_breakout[4].strip()
                        elif ')' not in vid_breakout[5].strip():
                            self.video_proto.resolution = vid_breakout[5].strip()
                        else:
                            self.video_proto.resolution = '1920x1080'

    def _download_video_to_working_directory(self, file_name):
        """
        Downloads the video to working directory from S3 and
        returns whether its successfully downloaded or not.

        Arguments:
            file_name: Name of the file when its in working directory
        """
        try:
            self.s3_key.get_contents_to_filename(os.path.join(self.node_work_directory, file_name))
            return True
        except S3DataError:
            LOGGER.error('[DISCOVERY] Error downloading the file into node working directory.')
            return False

    def _validate_file(self):
        """
        Validates a video file.
        Returns False if the video file is invalid, otherwise returns a valid Video object.
        """
        if self.studio_upload_id:
            video_set = Video.objects.filter(studio_id=self.studio_upload_id)
            if video_set.count() > 1:
                self.video_proto.veda_id = video_set.first().edx_id
                self.video_proto.video_orig_duration = video_set.first().video_orig_duration
                self.complete = True
                return
            elif video_set.count() == 0:
                LOGGER.error('[INGEST] Video {studio_id} not found in database. Should have been added already.'.format(
                    studio_id=self.studio_upload_id
                ))
                return

        video = Video.objects.get(studio_id=self.studio_upload_id)

        self.video_proto.valid = validate_video(videofile=self.full_filename)

        if self.video_proto.valid is True:
            self._gather_metadata()
        else:
            self._mark_file_corrupt(video)
            return

        return video

    def _mark_file_corrupt(self, video):
        """
        Mark a file as corrupt in the database.
        """
        video.video_trans_status = 'Corrupt File'
        video.video_active = False
        try:
            video.save()
        except:
            decoded_string = decode_to_ascii(self.video_proto.client_title)
            video.client_title = decoded_string
            video.save()
        self.complete = True
        LOGGER.info('[INGEST] {video_id} : Corrupt file, database record complete'.format(
            video_id=self.video_proto.veda_id
        ))

    def _mark_video_ready_for_task_fire(self, video):
        video.video_active = True
        video.video_trans_status = 'Ingest'
        video.video_trans_start = datetime.datetime.utcnow().replace(tzinfo=utc)
