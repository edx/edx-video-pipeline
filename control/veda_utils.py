"""
Quick and dirty output handling

"""
from __future__ import absolute_import
import boto.ses
import datetime
import subprocess

from control.control_env import *
from control.veda_encode import VedaEncode
from VEDA.utils import get_config


class EmailAlert(object):
    """
    Send alert emails VIA AWS SES for Course About Video Statuses

    """
    def __init__(self, **kwargs):
        self.auth_dict = get_config()
        self.body = kwargs.get('body', None)
        self.subject = kwargs.get('subject', None)
        self.additional_recipients = kwargs.get('additional_recipients', [])
        self.production_environment = self.auth_dict['environment'] == "production"

    def email_fault(self):
        self.subject = '[ VEDA ALERTING ] : ' + str(self.subject)
        self.body = 'There has been a fault:' + str(self.body)
        self.email()

    def email(self):
        if self.production_environment:
            try:
                conn = boto.ses.connect_to_region('us-east-1')
            except boto.exception.NoAuthHandlerFound:
                return

            recipients = self.additional_recipients.append(self.auth_dict['admin_email'])

            conn.send_email(
                self.auth_dict['veda_noreply_email'],
                self.subject,
                self.body,
                recipients
            )
        else:
            pass


class Output(object):
    """
    Display/Reporting methods
    """
    @staticmethod
    def _seconds_from_string(duration):
        if duration == 0 or duration is None:
            return 0
        hours = float(duration.split(':')[0])
        minutes = float(duration.split(':')[1])
        seconds = float(duration.split(':')[2])
        duration_seconds = (((hours * 60) + minutes) * 60) + seconds
        return duration_seconds


class Report(object):

    def __init__(self, **kwargs):
        self.auth_dict = get_config()
        self.status = kwargs.get('status', None)
        self.upload_serial = kwargs.get('upload_serial', None)
        self.youtube_id = kwargs.get('youtube_id', None)

    def upload_status(self):
        if self.upload_serial is None:
            return None
        if self.auth_dict is None:
            return None

        v1 = VedaUpload.objects.filter(
            video_serial=self.upload_serial
        )
        if len(v1) == 0:
            return None

        if len(self.youtube_id) > 0:
            email_status = ''

        if 'Duplicate' in self.status or 'Corrupt' in self.status:
            if v1[0].final_report is True:
                return None

            else:
                email_status = 'There has been a failure for the following reason : '
                email_status += self.status
                final_success = 'FAILED'
                self.youtube_id = ''

                VedaUpload.objects.filter(
                    pk=v1[0].pk
                ).update(
                    file_complete=False,
                    final_report=True,
                    file_valid=False
                )

        elif 'Complete' in self.status:
            """
            If completed, this will only go past once,
            as the URL will be added only once
            """
            email_status = 'This file is complete.'
            final_success = 'SUCCESS'
            VedaUpload.objects.filter(
                pk=v1[0].pk
            ).update(
                file_complete=True,
                final_report=True,
                file_valid=True,
                youtube_id=self.youtube_id
            )

        email_subject = 'VEDA / edX About Video Status Update : ' + str(final_success)

        email_body = (
            'This is an auto generated message:\n\n'
            'An edX partner uploaded a new about video:\n\n'
            'STATUS : ' + email_status + '\n\n'
        )
        if len(self.youtube_id) > 0:
            email_body += 'Youtube URL : https://www.youtube.com/watch?v=' + self.youtube_id + '\n\n'

        email_body += (
            'Filename : ' + v1[0].upload_filename + '\n'
            'Upload Date : ' + str(v1[0].upload_date) + '(UTC)\n'
            'Course Title (optional) : ' + v1[0].client_information + '\n'
            'edX Studio Course URL : ' + v1[0].edx_studio_url + '\n\n'
            'Please do not reply to this email.\n\n <<EOM'
        )

        EmailAlert(
            body=email_body,
            subject=email_subject,
            additional_recipients = [v1[0].status_email]
        ).email()


class VideoProto(object):
    """
    Video object abstraction,
    intended as a record before object is recorded in DB

    """
    def __init__(self, **kwargs):
        self.s3_filename = kwargs.get('s3_filename', None)
        self.client_title = kwargs.get('client_title', None)
        self.file_extension = kwargs.get('file_extension', None)
        self.platform_course_url = kwargs.get('platform_course_url', None)
        self.abvid_serial = kwargs.get('abvid_serial', None)
        """
        Determined Attrib
        """
        self.valid = False
        self.filesize = 0
        self.duration = 0
        self.bitrate = kwargs.get('bitrate', '0')
        self.resolution = None
        self.veda_id = kwargs.get('veda_id', None)
        self.val_id = kwargs.get('val_id', None)


class Metadata(object):
    """
    Centralized video metadata probe

    """
    def __init__(self, **kwargs):
        self.video_proto = kwargs.get('video_proto', None)
        self.video_object = kwargs.get(
            'video_object',
            None
        )
        self.node_work_directory = kwargs.get(
            'node_work_directory',
            WORK_DIRECTORY
        )
        self.full_filename = kwargs.get(
            'full_filename',
            None
        )
        self.freezing_bug = False
        self.val_status = None

    def _METADATA(self):
        """
        use st filesize for filesize
        Use "ffprobe" for other metadata
        ***
        """
        self.video_proto.filesize = os.stat(self.full_filename).st_size

        ff_command = ' '.join((
            FFPROBE,
            "\'" + self.full_filename + "\'"
        ))
        p = subprocess.Popen(ff_command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True)

        for line in iter(p.stdout.readline, b''):
            line = line.decode('utf-8')
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

    def _FAULT(self, video_object):
        """
        Find missing encodes
        """
        if self.video_object is None:
            return []
        # Check for object viability against prior findings
        if video_object.video_trans_status == 'Corrupt File':
            return []

        if video_object.video_trans_status == 'Review Reject':
            return []

        if video_object.video_trans_status == 'Review Hold':
            return []

        if video_object.video_active is False:

            return []

        # Determine encodes
        encode = VedaEncode(
            course_object=video_object.inst_class,
            veda_id=video_object.edx_id
        )

        encode_list = encode.determine_encodes()

        if encode_list is not None:
            if 'mobile_high' in encode_list:
                encode_list.remove('mobile_high')
            if 'audio_mp3' in encode_list:
                encode_list.remove('audio_mp3')
            if 'review' in encode_list:
                encode_list.remove('review')

        if encode_list is None or len(encode_list) == 0:
            self.val_status = 'file_complete'
            """
            File is complete!
            Check for data parity, and call done
            """
            if video_object.video_trans_status != 'File Complete':
                Video.objects.filter(
                    edx_id=video_object.edx_id
                ).update(
                    video_trans_status='File Complete',
                    video_trans_end=datetime.datetime.utcnow().replace(tzinfo=utc)
                )
            return []

        # get baseline // if there are == encodes and baseline,
        # mark file corrupt -- just run the query again with no veda_id.

        # kwarg override:
        if self.freezing_bug is False and self.val_status != 'file_complete':
            self.val_status = 'transcode_queue'
            return encode_list

        encode_two = VedaEncode(
            course_object=video_object.inst_class,
        )
        encode_two.determine_encodes()
        if len(encode_two.encode_list) == len(encode_list) and len(encode_list) > 1:
            # Mark File Corrupt, accounting for migrated legacy URLs
            url_test = URL.objects.filter(
                videoID=Video.objects.filter(
                    edx_id=video_object.edx_id
                ).latest()
            )

            if len(url_test) == 0:
                Video.objects.filter(
                    edx_id=video_object.edx_id
                ).update(
                    video_trans_status='Corrupt File',
                    video_trans_end=datetime.datetime.utcnow().replace(tzinfo=utc)
                )
                self.val_status = 'file_corrupt'
                return []

        self.val_status = 'transcode_queue'
        return encode_list
