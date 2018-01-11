"""
VEDA Delivery:
Determine the destination and upload to the appropriate
endpoint via the custom methods

"""
import datetime
import logging
import shutil
from os.path import expanduser
import sys

import boto
import boto.s3
from boto.s3.connection import S3Connection
import requests

from boto.exception import S3ResponseError, NoAuthHandlerFound
from boto.s3.key import Key
from django.core.urlresolvers import reverse

from control_env import *
from veda_deliver_cielo import Cielo24Transcript
from veda_deliver_youtube import DeliverYoutube
from VEDA_OS01 import utils
from VEDA_OS01.models import (TranscriptCredentials, TranscriptProvider,
                              TranscriptStatus)
from VEDA.utils import build_url, extract_course_org, get_config, delete_directory_contents
from veda_utils import ErrorObject, Metadata, Output, VideoProto
from veda_val import VALAPICall
from veda_video_validation import Validation

try:
    from control.veda_deliver_3play import ThreePlayMediaClient
except ImportError:
    from veda_deliver_3play import ThreePlayMediaClient

LOGGER = logging.getLogger(__name__)
# TODO: Remove this temporary logging to stdout
logging.basicConfig(stream=sys.stdout, level=logging.INFO)

try:
    boto.config.add_section('Boto')
except:
    pass
boto.config.set('Boto', 'http_socket_timeout', '100')

homedir = expanduser("~")


class VedaDelivery:

    def __init__(self, veda_id, encode_profile, **kwargs):
        self.veda_id = veda_id
        self.encode_profile = encode_profile
        self.auth_dict = kwargs.get('CONFIG_DATA', get_config())
        # Internal Methods
        self.video_query = None
        self.encode_query = None
        self.encoded_file = None
        self.node_work_directory = kwargs.get('node_work_directory', WORK_DIRECTORY)
        self.hotstore_url = None
        self.status = None
        self.endpoint_url = None
        self.video_proto = None
        self.val_status = None

    def run(self):
        """
        Check the destination, route via available methods,
        throw error if method is not extant
        """
        LOGGER.info('[VIDEO_DELIVER] {video_id} : {encode}'.format(video_id=self.veda_id, encode=self.encode_profile))
        if self.encode_profile == 'hls':
            # HLS encodes are a pass through
            self.hls_run()

        else:
            if os.path.exists(WORK_DIRECTORY):
                delete_directory_contents(WORK_DIRECTORY)

            self._INFORM_INTAKE()

            if self._VALIDATE() is False and \
                    self.encode_profile != 'youtube' and self.encode_profile != 'review':
                self._CLEANUP()
                return None

            self._DETERMINE_ROUTE()

        if self._VALIDATE_URL() is False and self.encode_profile != 'hls':
            # For youtube URLs (not able to validate right away)
            return

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
        u1.save()

        self.status = self._DETERMINE_STATUS()
        self._UPDATE_DATA()
        self._CLEANUP()

        # Transcription Process
        # We only want to generate transcripts for `desktop_mp4` profile.
        if self.encode_profile == 'desktop_mp4' and self.video_query.process_transcription:

            # 3PlayMedia
            if self.video_query.provider == TranscriptProvider.THREE_PLAY:
                self.start_3play_transcription_process()

            # Cielo24
            if self.video_query.provider == TranscriptProvider.CIELO24:
                self.cielo24_transcription_flow()

    def hls_run(self):
        """
        Get information about encode for URL validation/record

        """
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

        self.encoded_file = '/'.join((
            self.video_query.edx_id,
            '{file_name}.{ext}'.format(file_name=self.video_query.edx_id, ext='m3u8')
        ))

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

        try:
            conn = S3Connection()
            bucket = conn.get_bucket(self.auth_dict['veda_deliverable_bucket'])
        except NoAuthHandlerFound:
            LOGGER.error('[VIDEO_DELIVER] BOTO/S3 Communication error')
            return
        except S3ResponseError:
            LOGGER.error('[VIDEO_DELIVER] Invalid Storage Bucket')
            return
        source_key = bucket.get_key(self.encoded_file)
        if source_key is None:
            LOGGER.error('[VIDEO_DELIVER] S3 Intake Object NOT FOUND')
            return

        source_key.get_contents_to_filename(
            os.path.join(self.node_work_directory, self.encoded_file)
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
            self.val_status = 'file_complete'
        else:
            self.val_status = 'transcode_active'

        VAC = VALAPICall(
            video_proto=self.video_proto,
            val_status=self.val_status,
            endpoint_url=self.endpoint_url,
            encode_profile=self.encode_profile,
            CONFIG_DATA=self.auth_dict
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
        if not self.video_query.inst_class.s3_proc:
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
        org = extract_course_org(self.video_proto.platform_course_url[0])

        try:
            api_key = TranscriptCredentials.objects.get(org=org, provider=self.video_query.provider).api_key
        except TranscriptCredentials.DoesNotExist:
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

        # update transcript status for video.
        val_api_client = VALAPICall(video_proto=None, val_status=None)
        utils.update_video_status(
            val_api_client=val_api_client,
            video=self.video_query,
            status=TranscriptStatus.IN_PROGRESS
        )

        cielo24 = Cielo24Transcript(
            self.video_query,
            org,
            api_key,
            self.video_query.cielo24_turnaround,
            self.video_query.cielo24_fidelity,
            self.video_query.preferred_languages,
            s3_video_url,
            callback_base_url,
            self.auth_dict['cielo24_api_base_url'],
        )
        cielo24.start_transcription_flow()

    def start_3play_transcription_process(self):
        """
        3PlayMedia Transcription Flow
        """
        try:
            # Picks the first course from the list as there may be multiple
            # course runs in that list (i.e. all having the same org).
            org = extract_course_org(self.video_proto.platform_course_url[0])
            transcript_secrets = TranscriptCredentials.objects.get(org=org, provider=self.video_query.provider)

            # update transcript status for video.
            val_api_client = VALAPICall(video_proto=None, val_status=None)
            utils.update_video_status(
                val_api_client=val_api_client,
                video=self.video_query,
                status=TranscriptStatus.IN_PROGRESS
            )

            # Initialize 3playMedia client and start transcription process
            s3_video_url = build_url(
                self.auth_dict['s3_base_url'],
                self.auth_dict['edx_s3_endpoint_bucket'],
                self.encoded_file
            )
            callback_url = build_url(
                self.auth_dict['veda_base_url'],
                reverse(
                    '3play_media_callback',
                    args=[self.auth_dict['transcript_provider_request_token']]
                ),
                # Additional attributes that'll come back with the callback
                org=org,
                edx_video_id=self.video_query.studio_id,
                lang_code=self.video_query.source_language,
            )
            three_play_media = ThreePlayMediaClient(
                org=org,
                video=self.video_query,
                media_url=s3_video_url,
                api_key=transcript_secrets.api_key,
                api_secret=transcript_secrets.api_secret,
                callback_url=callback_url,
                turnaround_level=self.video_query.three_play_turnaround,
                three_play_api_base_url=self.auth_dict['three_play_api_base_url'],
            )
            three_play_media.generate_transcripts()

        except TranscriptCredentials.DoesNotExist:
            LOGGER.warning(
                'Transcript preference is not found for provider=%s, video=%s',
                self.video_query.provider,
                self.video_query.studio_id,
            )

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
