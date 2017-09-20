import logging
import os
import sys
import subprocess
import datetime
from datetime import timedelta
import time
import fnmatch
import django
from django.db.utils import DatabaseError
from django.utils.timezone import utc
from django.db import reset_queries
import uuid
import yaml
import hashlib


"""
Discovered file ingest/insert/job triggering

**NOTE**
Local Files, Migrated files are eliminated
This just takes discovered
    - About Vids
    - Studio Uploads
    - FTP Uploads
"""
from control_env import *
from veda_hotstore import Hotstore
from veda_video_validation import Validation
from veda_utils import ErrorObject, Output, Report
from veda_val import VALAPICall
from veda_encode import VedaEncode
import celeryapp

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


class VideoProto():

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

        # Determined Attributes
        self.valid = False
        self.filesize = 0
        self.duration = 0
        self.bitrate = None
        self.resolution = None
        self.veda_id = None
        self.hash_sum = None


class VedaIngest:

    def __init__(self, course_object, video_proto, **kwargs):
        self.course_object = course_object
        self.video_proto = video_proto
        self.auth_yaml = kwargs.get(
            'auth_yaml',
            os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                'instance_config.yaml'
            ),
        )
        self.auth_dict = self._READ_AUTH()

        # --- #
        self.node_work_directory = kwargs.get('node_work_directory', WORK_DIRECTORY)
        self.full_filename = kwargs.get('full_filename', None)
        self.complete = False
        self.archived = False

    def _READ_AUTH(self):
        if self.auth_yaml is None:
            return None
        if not os.path.exists(self.auth_yaml):
            return None

        with open(self.auth_yaml, 'r') as stream:
            try:
                auth_dict = yaml.load(stream)
                return auth_dict
            except yaml.YAMLError as exc:
                return None

    def insert(self):
        """
        NOTE:
        eliminate Ingest Field
        """
        self.database_record()
        self.val_insert()
        # --- #
        self.rename()
        self.archived = self.store()

        if self.video_proto.valid is False:
            self.abvid_report()
            self.complete = True
            if self.archived is True:
                os.remove(self.full_filename)
            return None

        self.queue_job()
        print '%s : [ %s ] : %s' % (
            str(datetime.datetime.utcnow()),
            self.video_proto.veda_id,
            'File Active'
        )
        Course.objects.filter(
            pk=self.course_object.pk
        ).update(
            previous_statechange=datetime.datetime.utcnow().replace(tzinfo=utc)
        )
        if self.archived is True:
            os.remove(self.full_filename)
        self.complete = True

    def queue_job(self):
        print '%s : [ %s ] : %s' % (
            str(datetime.datetime.utcnow()),
            self.video_proto.veda_id,
            'Remote Assimilate'
        )

        '''
        nouvelle:
        '''
        if self.auth_dict is None:
            ErrorObject().print_error(
                message='No Auth YAML Found'
            )
            return None

        # WRITE JOB QUEUEING
        En = VedaEncode(
            course_object=self.course_object,
            veda_id=self.video_proto.veda_id
        )
        self.encode_list = En.determine_encodes()

        if len(self.encode_list) == 0:
            return None

        """
        send job to queue
        """
        if self.video_proto.filesize > self.auth_dict['largefile_queue_barrier']:
            cel_queue = self.auth_dict['largefile_celery_queue']
        else:
            cel_queue = self.auth_dict['main_celery_queue']

        for e in self.encode_list:
            # print e
            veda_id = self.video_proto.veda_id
            encode_profile = e
            jobid = uuid.uuid1().hex[0:10]
            celeryapp.worker_task_fire.apply_async(
                (veda_id, encode_profile, jobid),
                queue=cel_queue
            )

        """
        Update Video Status
        """
        Video.objects.filter(
            edx_id=self.video_proto.veda_id
        ).update(
            video_trans_status='Queue'
        )

    def _METADATA(self):
        """
        use st filesize for filesize
        Use "ffprobe" for other metadata
        ***
        """
        self.video_proto.filesize = os.stat(self.full_filename).st_size

        self.video_proto.hash_sum = hashlib.md5(
            open(self.full_filename, 'rb').read()
        ).hexdigest()

        ff_command = ' '.join((
            FFPROBE,
            "\'" + self.full_filename + "\'"
        ))
        p = subprocess.Popen(ff_command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True)

        for line in iter(p.stdout.readline, b''):
            # print line
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
                            print v
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
        Start DB Inserts, Get Information
        """
        if self.video_proto.s3_filename is not None:
            self.full_filename = '/'.join((
                self.node_work_directory,
                self.video_proto.s3_filename
            ))

        if self.video_proto.abvid_serial is not None:
            self.full_filename = '/'.join((
                self.node_work_directory,
                self.video_proto.client_title
            ))

        if self.full_filename is None:
            self.full_filename = '/'.join((
                self.node_work_directory,
                self.video_proto.client_title
            ))

        if len(self.video_proto.file_extension) == 3:
            self.full_filename += "." + self.video_proto.file_extension

        if not os.path.exists(self.full_filename):
            ErrorObject().print_error(
                message='Ingest: File Not Found'
            )
            return None

        """
        Validate File
        """
        VV = Validation(videofile=self.full_filename)

        self.video_proto.valid = VV.validate()

        if self.video_proto.valid is True:
            self._METADATA()
        """
        DB Inserts
        """
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
            v1.provider = self.video_proto.provider
            v1.three_play_turnaround = self.video_proto.three_play_turnaround
            v1.cielo24_turnaround = self.video_proto.cielo24_turnaround
            v1.cielo24_fidelity = self.video_proto.cielo24_fidelity
            v1.preferred_languages = self.video_proto.preferred_languages

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
            LOGGER.exception('[VIDEO-PIPELINE] File Ingest - Cataloging of video=%s failed.', self.video_proto.veda_id)
            raise

    def val_insert(self):
        if self.video_proto.abvid_serial is not None:
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

        R = Report(
            status="File Corrupt on Ingest",
            upload_serial=self.video_proto.abvid_serial,
            youtube_id=''
        )
        R.upload_status()
        self.complete = True

    def rename(self):
        """
        Rename to VEDA ID,
        Backup in Hotstore
        """
        if self.video_proto.veda_id is None:
            self.video_proto.valid = False
            return None

        if self.video_proto.file_extension is None:
            os.rename(
                self.full_filename, os.path.join(
                    self.node_work_directory,
                    self.video_proto.veda_id
                )
            )
            self.full_filename = os.path.join(
                self.node_work_directory,
                self.video_proto.veda_id
            )

        else:
            os.rename(
                self.full_filename,
                os.path.join(
                    self.node_work_directory,
                    self.video_proto.veda_id + '.' + self.video_proto.file_extension
                )
            )
            self.full_filename = os.path.join(
                self.node_work_directory,
                self.video_proto.veda_id + '.' + self.video_proto.file_extension
            )

        os.system('chmod ugo+rwx ' + self.full_filename)

    def store(self):
        """
        Ingest File Backup / Archive Policy
        """
        H1 = Hotstore(
            video_proto=self.video_proto,
            upload_filepath=self.full_filename
        )
        return H1.upload()


def main():
    """
    VP = VideoProto()
    VI = VedaIngest(
        course_object='Mock',
        video_proto=VP,
        full_filename='/Users/gregmartin/Downloads/MIT15662T115-V016800.mov'
    )
    VI._METADATA()
    print VI.video_proto.resolution
    """
    pass


if __name__ == "__main__":
    sys.exit(main())
