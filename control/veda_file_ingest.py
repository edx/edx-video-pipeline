"""
Discovered file ingest/insert/job triggering

"""

import datetime
import logging
import subprocess

from django.db.utils import DatabaseError

from control_env import *
from VEDA.utils import get_config
from veda_heal import VedaHeal
from veda_hotstore import Hotstore
from VEDA_OS01.models import TranscriptStatus
from veda_utils import Report
from veda_val import VALAPICall
from veda_video_validation import Validation

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
        self.veda_id = None


class VedaIngest(object):

    def __init__(self, course_object, video_proto, **kwargs):
        self.course_object = course_object
        self.video_proto = video_proto
        self.auth_dict = get_config()
        self.node_work_directory = kwargs.get('node_work_directory', WORK_DIRECTORY)
        self.full_filename = kwargs.get('full_filename', None)
        self.complete = False
        self.archived = False

    def insert(self):
        self.database_record()
        self.val_insert()
        self.rename()
        self.archived = self.store()

        if self.video_proto.valid is False:
            self.abvid_report()
            self.complete = True
            if self.archived is True:
                os.remove(self.full_filename)
            return None

        LOGGER.info('[VIDEO_INGEST : Ingested] {video_id} : {datetime}'.format(
            video_id=self.video_proto.veda_id,
            datetime=str(datetime.datetime.utcnow()))
        )

        self.queue_job()
        Course.objects.filter(
            pk=self.course_object.pk
        ).update(
            previous_statechange=datetime.datetime.utcnow().replace(tzinfo=utc)
        )
        if self.archived is True:
            os.remove(self.full_filename)
        self.complete = True

    def queue_job(self):
        # TODO: Break heal method listed here out into helper util
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

    def database_record(self):
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
            LOGGER.exception('[VIDEO_INGEST] File Not Found %s', self.video_proto.veda_id)
            return

        """
        Validate File
        """
        VV = Validation(videofile=self.full_filename)

        self.video_proto.valid = VV.validate()

        if self.video_proto.valid is True:
            self._gather_metadata()

        # DB Inserts
        if self.video_proto.s3_filename:
            video = Video.objects.filter(studio_id=self.video_proto.s3_filename).first()
            if video:
                # Protect against crash/duplicate inserts, won't insert object
                self.video_proto.veda_id = video[0].edx_id
                self.video_proto.video_orig_duration = video[0].video_orig_duration
                self.complete = True
                return

        v1 = Video(inst_class=self.course_object)
        """
        Generate veda_id / update course record
        * Note: defensive against the possibility of later passing in an ID
        """
        if self.video_proto.veda_id is None:
            lsid = self.course_object.last_vid_number + 100
            self.video_proto.veda_id = self.course_object.institution
            self.video_proto.veda_id += self.course_object.edx_classid
            self.video_proto.veda_id += self.course_object.semesterid
            self.video_proto.veda_id += "-V" + str(lsid).zfill(6)

            """
            Update Course Record
            """
            self.course_object.last_vid_number = lsid
            self.course_object.save()

        v1.edx_id = self.video_proto.veda_id

        v1.video_orig_extension = self.video_proto.file_extension
        v1.studio_id = self.video_proto.s3_filename
        v1.client_title = self.video_proto.client_title
        v1.abvid_serial = self.video_proto.abvid_serial

        if self.video_proto.valid is False:
            """
            Invalid File, Save, exit
            """
            v1.video_trans_status = 'Corrupt File'
            v1.video_active = False
            try:
                v1.save()
            except:
                """
                decode to ascii
                """
                char_string = self.video_proto.client_title
                string_len = len(char_string)
                s1 = 0
                final_string = ""
                while string_len > s1:
                    try:
                        char_string[s1].decode('ascii')
                        final_string += char_string[s1]
                    except:
                        final_string += "?"
                    s1 += 1
                v1.client_title = final_string
                v1.save()
            self.complete = True
            return None

        # Update transcription preferences for the Video
        if self.video_proto.process_transcription:
            v1.process_transcription = self.video_proto.process_transcription
            v1.transcript_status = TranscriptStatus.PENDING
            v1.provider = self.video_proto.provider
            v1.three_play_turnaround = self.video_proto.three_play_turnaround
            v1.cielo24_turnaround = self.video_proto.cielo24_turnaround
            v1.cielo24_fidelity = self.video_proto.cielo24_fidelity
            v1.preferred_languages = self.video_proto.preferred_languages
            v1.source_language = self.video_proto.source_language

        """
        Files Below are all valid
        """
        v1.video_orig_filesize = self.video_proto.filesize
        v1.video_orig_duration = self.video_proto.duration
        v1.video_orig_bitrate = self.video_proto.bitrate
        v1.video_orig_resolution = self.video_proto.resolution

        """
        Ready for Task Fire
        """
        v1.video_active = True
        v1.video_trans_status = 'Ingest'
        v1.video_trans_start = datetime.datetime.utcnow().replace(tzinfo=utc)

        """
        Save / Decode / Update Course
        """
        try:
            v1.save()
        except DatabaseError:
            # in case if the client title's length is too long
            char_string = self.video_proto.client_title
            string_len = len(char_string)
            s1 = 0
            final_string = ""
            while string_len > s1:
                try:
                    char_string[s1].decode('ascii')
                    final_string += char_string[s1]
                except:
                    final_string += "?"
                s1 += 1
            v1.client_title = final_string
            v1.save()

        except Exception:
            # Log the exception and raise.
            LOGGER.exception('[VIDEO_INGEST] - Cataloging of video=%s failed.', self.video_proto.veda_id)
            raise

    def val_insert(self):
        if self.video_proto.abvid_serial:
            return None

        if self.video_proto.valid is False:
            val_status = 'file_corrupt'
        else:
            val_status = 'ingest'

        VAC = VALAPICall(
            video_proto=self.video_proto,
            val_status=val_status,
            platform_course_url=""  # Empty record for initial status update
        )
        VAC.call()

    def abvid_report(self):
        if self.video_proto.abvid_serial is None:
            return None

        email_report = Report(
            status="File Corrupt on Ingest",
            upload_serial=self.video_proto.abvid_serial,
            youtube_id=''
        )
        email_report.upload_status()
        self.complete = True

    def rename(self):
        """
        Rename to VEDA ID,

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

    def store(self):
        """
        Ingest File Backup / Archive Policy
        """
        H1 = Hotstore(
            video_proto=self.video_proto,
            upload_filepath=self.full_filename
        )
        return H1.upload()
