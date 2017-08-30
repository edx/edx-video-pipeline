
import datetime
import ftplib
import logging
import os
import shutil
import sys
from os.path import expanduser

import boto
import boto.s3
import requests
import yaml
from boto.exception import S3ResponseError
from boto.s3.key import Key
from django.core.urlresolvers import reverse

import veda_deliver_xuetang
from control_env import *
from veda_deliver_cielo import Cielo24Transcript
from veda_deliver_youtube import DeliverYoutube
from VEDA_OS01 import utils
from VEDA_OS01.models import (TranscriptPreferences, TranscriptProvider,
                              VideoStatus)
from VEDA_OS01.utils import build_url
from veda_utils import ErrorObject, Metadata, Output, VideoProto
from veda_val import VALAPICall
from veda_video_validation import Validation
from watchdog import Watchdog

LOGGER = logging.getLogger(__name__)



try:
    boto.config.add_section('Boto')
except:
    pass
boto.config.set('Boto', 'http_socket_timeout', '100')


"""
VEDA Delivery class - determine the destination
and upload to the appropriate endpoint via the approp. methods


"""
homedir = expanduser("~")


watchdog_time = 10.0


class VedaDelivery:

    def __init__(self, veda_id, encode_profile, **kwargs):
        self.veda_id = veda_id
        self.encode_profile = encode_profile

        self.auth_yaml = kwargs.get(
            'auth_yaml',
            os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                'instance_config.yaml'
            ),
        )
        self.auth_dict = self._READ_YAML(self.auth_yaml)
        # Internal Methods
        self.video_query = None
        self.encode_query = None
        self.encoded_file = None
        self.node_work_directory = kwargs.get('node_work_directory', WORK_DIRECTORY)
        self.hotstore_url = None
        self.status = None
        self.endpoint_url = None
        self.video_proto = None

    def _READ_YAML(self, read_yaml):
        if read_yaml is None:
            return None
        if not os.path.exists(read_yaml):
            return None

        with open(read_yaml, 'r') as stream:
            try:
                return_dict = yaml.load(stream)
                return return_dict
            except yaml.YAMLError as exc:
                return None

    def run(self):
        """
        Check the destination, route via available methods,
        throw error if method is not extant
        """
        if self.encode_profile == 'hls':
            self.video_query = Video.objects.filter(edx_id=self.veda_id).latest()
            self.video_proto = VideoProto(
                veda_id=self.video_query.edx_id,
                val_id=self.video_query.studio_id,
                client_title=self.video_query.client_title,
                duration=self.video_query.video_orig_duration,
                bitrate='0',
                s3_filename=self.video_query.studio_id
            )
            self.encode_query = Encode.objects.get(
                product_spec=self.encode_profile
            )

            Video.objects.filter(
                edx_id=self.video_query.edx_id
            ).update(
                video_trans_status='Progress'
            )

            self.encoded_file = '/'.join((
                self.video_query.edx_id,
                self.video_query.edx_id + '.m3u8'
            ))

        else:
            if os.path.exists(WORK_DIRECTORY):
                shutil.rmtree(WORK_DIRECTORY)
                os.mkdir(WORK_DIRECTORY)

            self._INFORM_INTAKE()
            """
            Update Video Status
            """
            Video.objects.filter(
                edx_id=self.video_proto.veda_id
            ).update(
                video_trans_status='Progress'
            )

            if self._VALIDATE() is False and \
                    self.encode_profile != 'youtube' and self.encode_profile != 'review':
                self._CLEANUP()
                return None

            self._DETERMINE_ROUTE()

        if self._VALIDATE_URL() is False and self.encode_profile != 'hls':
            """
            Remember: youtube will return 'None'
            """
            print 'ERROR: Invalid URL // Fail Out'
            return None

        """
        if present, set cloudfront distribution
        example endpoint:
            https://d2f1egay8yehza.cloudfront.net/V004300_MB1.mp4

        """
        if self.encode_profile == 'youtube':
            self._CLEANUP()
            return None
        if self.encode_profile == 'review':
            return None

        if self.auth_dict['edx_cloudfront_prefix'] is not None:

            self.endpoint_url = '/'.join((
                self.auth_dict['edx_cloudfront_prefix'],
                self.encoded_file
            ))

        u1 = URL(
            videoID=self.video_query,
            encode_profile=self.encode_query,
            encode_url=self.endpoint_url,
            url_date=datetime.datetime.utcnow().replace(tzinfo=utc),
        )
        u1.encode_duration = self.video_proto.duration
        u1.encode_bitdepth = self.video_proto.bitrate
        u1.encode_size = self.video_proto.filesize
        u1.md5_sum = self.video_proto.hash_sum
        u1.save()

        """
        Transcript, Xuetang
        """

        self._XUETANG_ROUTE()

        self.status = self._DETERMINE_STATUS()

        self._UPDATE_DATA()

        self._CLEANUP()

        self._THREEPLAY_UPLOAD()
        # Transcription Process
        # We only want to generate transcripts for `desktop_mp4` profile.
        if self.encode_profile == 'desktop_mp4' and self.video_query.process_transcription:

            # 3PlayMedia
            if self.video_query.provider == TranscriptProvider.THREE_PLAY:
                self.start_3play_transcription_process()

            # Cielo24
            if self.video_query.provider == TranscriptProvider.CIELO24:
                self.cielo24_transcription_flow()


    def _INFORM_INTAKE(self):
        """
        Collect all salient metadata and
        intake the file into the purvey of the methods
        """
        self.video_proto = VideoProto()
        self.video_query = Video.objects.filter(edx_id=self.veda_id).latest()
        self.encode_query = Encode.objects.get(
            product_spec=self.encode_profile
        )

        self.encoded_file = '%s_%s.%s' % (
            self.veda_id,
            self.encode_query.encode_suffix,
            self.encode_query.encode_filetype
        )

        self.hotstore_url = '/'.join((
            'https:/',
            's3.amazonaws.com',
            self.auth_dict['veda_deliverable_bucket'],
            self.encoded_file
        ))
        os.system(
            ' '.join((
                'wget -O',
                os.path.join(self.node_work_directory, self.encoded_file),
                self.hotstore_url
            ))
        )
        """
        Utilize Metadata method in veda_utils -- can later
        move this out into it's own utility method
        """
        VM = Metadata(
            video_proto=self.video_proto,
            full_filename=os.path.join(
                self.node_work_directory,
                self.encoded_file
            )
        )
        VM._METADATA()

        if not isinstance(self.video_proto.duration, int) and ':' not in self.video_proto.duration:
            print 'Duration Failure'
            return

        self.video_proto.duration = Output._seconds_from_string(
            duration=self.video_proto.duration
        )
        self.video_proto.s3_filename = self.video_query.studio_id
        """
        Further information for VAL
        """
        self.video_proto.veda_id = self.video_query.edx_id
        self.video_proto.platform_course_url = \
            [i for i in self.video_query.inst_class.local_storedir.split(',')]
        self.video_proto.client_title = self.video_query.client_title

    def _VALIDATE(self):
        V = Validation(
            videofile=os.path.join(
                self.node_work_directory,
                self.encoded_file
            ),
            mezzanine=False,
            veda_id=self.veda_id
        )
        return V.validate()

    def _CLEANUP(self):
        """
        check for workflow simplification
        """
        if self.auth_dict['veda_deliverable_bucket'] == \
                self.auth_dict['edx_s3_endpoint_bucket']:
            return
        try:
            conn = boto.connect_s3()
        except S3ResponseError:
            return
        del_bucket = conn.get_bucket(
            self.auth_dict['veda_deliverable_bucket']
        )
        k = Key(del_bucket)
        k.key = self.encoded_file
        k.delete()

    def _DETERMINE_STATUS(self):
        """
        Get status from heal method
        """
        VF = Metadata(
            video_object=self.video_query
        )
        encode_list = VF._FAULT(
            video_object=self.video_query
        )
        if len(encode_list) == 0:
            return 'Complete'
        else:
            return 'Progress'

    def _UPDATE_DATA(self):
        if self.status is None:
            return None

        Video.objects.filter(
            pk=self.video_query.pk
        ).update(
            video_trans_status=self.status
        )

        if self.encode_profile == 'review':
            return None

        if self.status == 'Complete':
            val_status = 'file_complete'
        else:
            val_status = 'transcode_active'
        print self.video_proto.val_id
        VAC = VALAPICall(
            video_proto=self.video_proto,
            val_status=val_status,
            endpoint_url=self.endpoint_url,
            encode_profile=self.encode_profile
        )
        VAC.call()

    def _VALIDATE_URL(self):
        """
        Protect against youtube, which does not supply
        a valid endpoint URl right away, and is covered in
        another method...we'll return 'None' for that
        """
        if self.endpoint_url is None:
            return False

        u = requests.head(self.endpoint_url)
        if u.status_code > 399:
            return False

        return True

    def _DETERMINE_ROUTE(self):
        """
        cascade to methods, check for eligibility
        within methods (eg, 3play, etc)

        """
        if not os.path.exists(
            os.path.join(
                self.node_work_directory,
                self.encoded_file
            )
        ):
            print 'WARNING -- NO FILE'
            return None
        '''
        Destination Nicks:
            S31
            YT1
            YTR
            LBO
            HLS
        '''
        if self.encode_query.encode_destination.destination_nick == 'S31' or self.encode_profile == 'override':
            delivered = self.AWS_UPLOAD()
            return delivered

        elif self.encode_query.encode_destination.destination_nick == 'YT1':
            self.YOUTUBE_SFTP()

        elif self.encode_query.encode_destination.destination_nick == 'YTR':
            self.YOUTUBE_SFTP(review=True)

        else:
            """
            Throw error
            """
            ErrorObject.print_error(
                message='Deliverable - No Method',
            )
            return None

    def AWS_UPLOAD(self):
        """
        TODO: Let's make this workflow simpler, we can get a duration
        from the hotstore url, check and delete if needed

        For now, old style workflow with checks and deletes at end
        """
        if self.video_query.inst_class.s3_proc is False and \
                self.video_query.inst_class.mobile_override is False:
            return False

        if self.video_proto.filesize < self.auth_dict['multi_upload_barrier']:
            """
            Upload single part
            """
            if self._BOTO_SINGLEPART() is False:
                return False

        else:
            """
            Upload multipart
            """
            if self._BOTO_MULTIPART() is False:
                return False

        self.endpoint_url = '/'.join((
            'https://s3.amazonaws.com',
            self.auth_dict['edx_s3_endpoint_bucket'],
            self.encoded_file
        ))
        return True

    def _BOTO_SINGLEPART(self):
        """
        Upload single part (under threshold in node_config)
        node_config MULTI_UPLOAD_BARRIER
        """
        try:
            conn = boto.connect_s3()
        except S3ResponseError:
            ErrorObject.print_error(
                message='Deliverable Fail: s3 Connection Error\n \
                Check node_config DELIVERY_ENDPOINT'
            )
            return False
        delv_bucket = conn.get_bucket(
            self.auth_dict['edx_s3_endpoint_bucket']
        )
        upload_key = Key(delv_bucket)
        upload_key.key = os.path.basename(os.path.join(
            self.node_work_directory,
            self.encoded_file
        ))
        headers = {"Content-Disposition": "attachment"}
        upload_key.set_contents_from_filename(
            os.path.join(
                self.node_work_directory,
                self.encoded_file
            ),
            headers=headers,
            replace=True
        )
        upload_key.set_acl('public-read')
        return True

    def _BOTO_MULTIPART(self):
        """
        Split file into chunks, upload chunks

        NOTE: this should never happen, as your files should be much
        smaller than this, but one never knows
        """
        path_to_multipart = self.node_work_directory
        filename = os.path.basename(self.encoded_file)

        if not os.path.exists(
            os.path.join(path_to_multipart, filename.split('.')[0])
        ):
            os.mkdir(os.path.join(path_to_multipart, filename.split('.')[0]))

        os.chdir(os.path.join(path_to_multipart, filename.split('.')[0]))
        """
        Split File into chunks
        """
        split_command = 'split -b5m -a5'  # 5 part names of 5mb
        sys.stdout.write('%s : %s\n' % (filename, 'Generating Multipart'))
        os.system(' '.join((split_command, self.deliverable)))
        sys.stdout.flush()

        """
        Connect to s3
        """
        try:
            c = boto.connect_s3()
        except S3ResponseError:
            ErrorObject.print_error(
                message='Deliverable Fail: s3 Connection Error\n \
                Check node_config DELIVERY_ENDPOINT'
            )
            return False
        b = c.lookup(self.auth_dict['edx_s3_endpoint_bucket'])
        if b is None:
            ErrorObject.print_error(
                message='Deliverable Fail: s3 Connection Error\n \
                Check node_config DELIVERY_ENDPOINT'
            )
            return False

        """
        Upload and stitch parts
        """
        mp = b.initiate_multipart_upload(filename)
        headers = {
            "Content-Disposition": "attachment"
        }
        x = 1
        for file in sorted(
            os.listdir(
                os.path.join(
                    path_to_multipart,
                    filename.split('.')[0]
                )
            )
        ):
            sys.stdout.write('%s : %s\r' % (file, 'uploading part'))
            fp = open(file, 'rb')
            mp.upload_part_from_file(fp, x, headers=headers)
            fp.close()
            sys.stdout.flush()
            x += 1

        sys.stdout.write('\n')
        mp.complete_upload()
        mp.set_acl('public-read')

        """
        Clean up multipart
        """
        shutil.rmtree(os.path.join(path_to_multipart, filename.split('.')[0]))
        os.chdir(homedir)
        return True

    def cielo24_transcription_flow(self):
        """
        Cielo24 transcription flow.
        """
        org = utils.extract_course_org(self.video_proto.platform_course_url[0])

        try:
            api_key = TranscriptPreferences.objects.get(org=org, provider=self.video_query.provider).api_key
        except TranscriptPreferences.DoesNotExist:
            LOGGER.warn('[cielo24] Unable to find api_key for org=%s', org)
            return None

        s3_video_url = build_url(
            self.auth_dict['s3_base_url'],
            self.auth_dict['edx_s3_endpoint_bucket'],
            self.encoded_file
        )

        callback_base_url = build_url(
            self.auth_dict['veda_base_url'],
            reverse(
                'cielo24_transcript_completed',
                args=[self.auth_dict['transcript_provider_request_token']]
            )
        )

        # update transcript status for video in edx-val
        VALAPICall(video_proto=None, val_status=None).update_video_status(
            self.video_query.studio_id, VideoStatus.TRANSCRIPTION_IN_PROGRESS
        )

        cielo24 = Cielo24Transcript(
            self.video_query,
            org,
            api_key,
            self.video_query.cielo24_turnaround,
            self.video_query.cielo24_fidelity,
            self.video_query.preferred_languages,
            s3_video_url,
            callback_base_url
        )
        cielo24.start_transcription_flow()

    def _THREEPLAY_UPLOAD(self):

        if self.video_query.inst_class.tp_proc is False:
            return None
        if self.video_query.inst_class.mobile_override is False:
            if self.encode_profile != 'desktop_mp4':
                return None

        ftp1 = ftplib.FTP(
            self.auth_dict['threeplay_ftphost']
        )
        user = self.video_query.inst_class.tp_username.strip()
        passwd = self.video_query.inst_class.tp_password.strip()
        try:
            ftp1.login(user, passwd)
        except:
            ErrorObject.print_error(
                message='3Play Authentication Failure'
            )
        try:
            ftp1.cwd(
                self.video_query.inst_class.tp_speed
            )
        except:
            ftp1.mkd(
                self.video_query.inst_class.tp_speed
            )
            ftp1.cwd(
                self.video_query.inst_class.tp_speed
            )
            os.chdir(self.node_work_directory)

        ftp1.storbinary(
            'STOR ' + self.encoded_file,
            open(os.path.join(
                self.node_work_directory,
                self.encoded_file
            ), 'rb')
        )

        os.chdir(homedir)

    def _XUETANG_ROUTE(self):
        if self.video_query.inst_class.xuetang_proc is False:
            return None

        if self.video_query.inst_class.mobile_override is False:
            if self.encode_profile != 'desktop_mp4':
                return None
        # TODO: un-hardcode
        reformat_url = self.endpoint_url.replace(
            'https://d2f1egay8yehza.cloudfront.net/',
            'http://s3.amazonaws.com/edx-course-videos/'
        )

        prepared_url = veda_deliver_xuetang.prepare_create_or_update_video(
            edx_url=reformat_url,
            download_urls=[reformat_url],
            md5sum=self.video_proto.hash_sum
        )

        w = Watchdog(10)
        w.StartWatchdog()

        try:
            res = veda_deliver_xuetang._submit_prepared_request(
                prepared_url
            )
        except (TypeError):
            ErrorObject.print_error(
                message='[ALERT] - Xuetang Send Failure'
            )
            return None
        w.StopWatchdog()

        if res.status_code == 200 and \
                res.json()['status'] != 'failed':
            URL.objects.filter(
                encode_url=self.endpoint_url
            ).update(
                xuetang_input=True
            )

        print str(res.status_code) + " : XUETANG STATUS CODE"

    def YOUTUBE_SFTP(self, review=False):
        if self.video_query.inst_class.yt_proc is False:
            if self.video_query.inst_class.review_proc is False:
                print 'NO YOUTUBE'
                return None

        DY = DeliverYoutube(
            veda_id=self.video_query.edx_id,
            encode_profile=self.encode_profile
        )
        DY.upload()


def main():
    pass


if __name__ == '__main__':
    sys.exit(main())
