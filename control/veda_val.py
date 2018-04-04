"""
Send data to VAL, either Video ID data or endpoint URLs

"""

import logging
import requests
import ast
import json

from control_env import *
from control.veda_utils import Output, VideoProto

from VEDA_OS01.utils import ValTranscriptStatus

LOGGER = logging.getLogger(__name__)
requests.packages.urllib3.disable_warnings()

'''
"upload": _UPLOADING,
"ingest": _IN_PROGRESS,
"transcode_queue": _IN_PROGRESS,
"transcode_active": _IN_PROGRESS,
"file_delivered": _COMPLETE,
"file_complete": _COMPLETE,
"file_corrupt": _FAILED,
"pipeline_error": _FAILED,
"invalid_token": _INVALID_TOKEN,
"duplicate" : _DUPLICATE,
"imported": _IMPORTED,

'''

FILE_COMPLETE_STATUSES = (
    'file_complete',
    ValTranscriptStatus.TRANSCRIPT_READY,
    ValTranscriptStatus.TRANSCRIPTION_IN_PROGRESS,
)


class VALAPICall(object):

    def __init__(self, video_proto, val_status, **kwargs):
        """VAL Data"""
        self.val_status = val_status
        self.platform_course_url = kwargs.get('platform_course_url', [])

        """VEDA Data"""
        self.video_proto = video_proto
        self.video_object = kwargs.get('video_object', None)
        self.encode_profile = kwargs.get('encode_profile', None)

        """if sending urls"""
        self.endpoint_url = kwargs.get('endpoint_url', None)
        self.encode_data = []
        self.val_profile = None

        """Generated"""
        self.val_token = None
        self.val_data = None
        self.headers = None

        """Credentials"""
        self.auth_dict = kwargs.get('CONFIG_DATA', self._AUTH())

    def call(self):
        if not self.auth_dict:
            return None

        """
        Errors covered in other methods
        """
        if not self.val_token:
            self.val_tokengen()
        if self.video_object:
            self.send_object_data()
            return
        if self.video_proto is not None:
            self.send_val_data()

    def _AUTH(self):
        return get_config()

    def val_tokengen(self):
        """
        Generate a API token for VAL
        """
        payload = {
            'grant_type': 'password',
            'client_id': self.auth_dict['val_client_id'],
            'client_secret': self.auth_dict['val_secret_key'],
            'username': self.auth_dict['val_username'],
            'password': self.auth_dict['val_password'],
        }
        r = requests.post(self.auth_dict['val_token_url'], data=payload, timeout=self.auth_dict['global_timeout'])

        if r.status_code != 200:
            LOGGER.error('[API] : VAL Token generation')
            return

        self.val_token = ast.literal_eval(r.text)['access_token']
        self.headers = {
            'Authorization': 'Bearer ' + self.val_token,
            'content-type': 'application/json'
        }

    def send_object_data(self):
        """
        Rather than rewrite the protocol to fit the veda models,
        we'll shoehorn the model into the VideoProto model
        """
        self.video_proto = VideoProto()

        self.video_proto.s3_filename = self.video_object.studio_id
        self.video_proto.veda_id = self.video_object.edx_id
        self.video_proto.client_title = self.video_object.client_title
        if self.video_proto.client_title is None:
            self.video_proto.client_title = ''
        self.video_proto.duration = self.video_object.video_orig_duration

        self.send_val_data()

    def send_val_data(self):
        """
        VAL is very tetchy -- it needs a great deal of specific info or it will fail
        """
        '''
        sending_data = {
            encoded_videos = [{
                url="https://testurl.mp4",
                file_size=8499040,
                bitrate=131,
                profile="override",
                }, {...},],
            client_video_id = "This is a VEDA-VAL Test",
            courses = [ "TEST", "..." ],
            duration = 517.82,
            edx_video_id = "TESTID",
            status = "transcode_active"
            }
        ## "POST" for new objects to 'video' root url
        ## "PUT" for extant objects to video/id --
            cannot send duplicate course records
        '''
        if not self.val_token:
            return False

        if self.video_proto.s3_filename is None or \
                len(self.video_proto.s3_filename) == 0:
            self.video_proto.val_id = self.video_proto.veda_id

        else:
            self.video_proto.val_id = self.video_proto.s3_filename

        if self.val_status != 'invalid_token':
            self.video_object = Video.objects.filter(
                edx_id=self.video_proto.veda_id
            ).latest()

        """
        Data Cleaning
        """
        if self.video_proto.platform_course_url is None:
            self.video_proto.platform_course_url = []

        if not isinstance(self.video_proto.platform_course_url, list):
            self.video_proto.platform_course_url = [self.video_proto.platform_course_url]

        try:
            self.video_object.video_orig_duration
        except NameError:
            self.video_object.video_orig_duration = 0
            self.video_object.duration = 0.0

        except AttributeError:
            pass

        if not isinstance(self.video_proto.duration, float) and self.val_status != 'invalid_token':
            self.video_proto.duration = Output._seconds_from_string(
                duration=self.video_object.video_orig_duration
            )

        """
        Sort out courses
        """
        val_courses = []
        if self.val_status != 'invalid_token':
            for f in self.video_object.inst_class.local_storedir.split(','):
                if f.strip() not in val_courses and len(f.strip()) > 0:
                    val_courses.append({f.strip(): None})

        for g in self.video_proto.platform_course_url:
            if g.strip() not in val_courses:
                val_courses.append({g.strip(): None})

        self.val_data = {
            'client_video_id': self.video_proto.client_title,
            'duration': self.video_proto.duration,
            'edx_video_id': self.video_proto.val_id,
            'courses': val_courses
        }

        r1 = requests.get(
            '/'.join((
                self.auth_dict['val_api_url'],
                self.video_proto.val_id
            )),
            headers=self.headers,
            timeout=self.auth_dict['global_timeout']
        )

        if r1.status_code != 200 and r1.status_code != 404:
            LOGGER.error('[API] : VAL Communication')
            return

        if r1.status_code == 404:
            self.send_404()

        elif r1.status_code == 200:
            val_api_return = ast.literal_eval(r1.text.replace('null', 'None'))
            self.send_200(val_api_return)

        """
        Update Status
        """
        url_query = URL.objects.filter(
            videoID=Video.objects.filter(
                edx_id=self.video_proto.veda_id
            )
        )
        for u in url_query:
            URL.objects.filter(pk=u.pk).update(val_input=True)

    def profile_determiner(self, val_api_return):
        """
        Determine VAL profile data, from return/encode submix

        """
        # Defend against old/deprecated encodes
        try:
            self.auth_dict['val_profile_dict'][self.encode_profile]
        except KeyError:
            return
        if self.endpoint_url:
            for p in self.auth_dict['val_profile_dict'][self.encode_profile]:

                self.encode_data.append(dict(
                    url=self.endpoint_url,
                    file_size=self.video_proto.filesize,
                    bitrate=int(self.video_proto.bitrate.split(' ')[0]),
                    profile=p
                ))

        test_list = []
        if self.video_proto.veda_id:
            url_query = URL.objects.filter(
                videoID=Video.objects.filter(
                    edx_id=self.video_proto.veda_id
                ).latest()
            )
            for u in url_query:
                final = URL.objects.filter(
                    encode_profile=u.encode_profile,
                    videoID=u.videoID
                ).latest()

                if final.encode_profile.product_spec == 'review':
                    pass
                else:
                    try:
                        self.auth_dict['val_profile_dict'][final.encode_profile.product_spec]
                    except KeyError:
                        return
                    for p in self.auth_dict['val_profile_dict'][final.encode_profile.product_spec]:
                        test_list.append(dict(
                            url=str(final.encode_url),
                            file_size=final.encode_size,
                            bitrate=int(final.encode_bitdepth.split(' ')[0]),
                            profile=str(p)
                        ))

        for t in test_list:
            if t['profile'] not in [g['profile'] for g in self.encode_data]:
                self.encode_data.append(t)

        if len(val_api_return) == 0:
            return

        """
        All URL Records Deleted (for some reason)
        """
        if len(self.encode_data) == 0:
            return

        for i in val_api_return['encoded_videos']:
            if i['profile'] not in [g['profile'] for g in self.encode_data]:
                self.encode_data.append(i)

        return

    @staticmethod
    def should_update_status(encode_list, val_status):
        """
        Check if we need to update video status in val

        Arguments:
            encode_list (list): list of video encodes
            val_status (unicode): val status
        """
        if len(encode_list) == 0 and val_status in FILE_COMPLETE_STATUSES:
            return False

        return True

    def send_404(self):
        """
        Generate new VAL ID
        """
        self.profile_determiner(val_api_return=[])

        self.val_data['status'] = self.val_status

        if self.should_update_status(self.encode_data, self.val_status) is False:
            return None

        sending_data = dict(
            encoded_videos=self.encode_data,
            **self.val_data
        )

        r2 = requests.post(
            self.auth_dict['val_api_url'] + '/',
            data=json.dumps(sending_data),
            headers=self.headers,
            timeout=self.auth_dict['global_timeout']
        )

        if r2.status_code > 299:
            LOGGER.error('[API] : VAL POST/PUT {code}'.format(code=r2.status_code))

    def send_200(self, val_api_return):
        """
        VAL ID is previously extant
        just update
        ---
        VAL will not allow duped studio urls to be sent,
        so we must scrub the data
        """
        for retrieved_course in val_api_return['courses']:
            for course in list(self.val_data['courses']):
                if retrieved_course.keys() == course.keys():
                    self.val_data['courses'].remove(course)

        self.profile_determiner(val_api_return=val_api_return)
        self.val_data['status'] = self.val_status
        """
        Double check for profiles in case of overwrite
        """
        sending_data = dict(
            encoded_videos=self.encode_data,
            **self.val_data
        )
        """
        Make Request, finally
        """
        if self.should_update_status(self.encode_data, self.val_status) is False:
            return None

        r4 = requests.put(
            '/'.join((
                self.auth_dict['val_api_url'],
                self.video_proto.val_id,
            )),
            data=json.dumps(sending_data),
            headers=self.headers,
            timeout=self.auth_dict['global_timeout']
        )
        LOGGER.info('[API] {id} : {status} sent to VAL {code}'.format(
            id=self.video_proto.val_id,
            status=self.val_status,
            code=r4.status_code)
        )
        if r4.status_code > 299:
            LOGGER.error('[API] : VAL POST/PUT : {status}'.format(status=r4.status_code))

    def update_val_transcript(self, video_id, lang_code, name, transcript_format, provider):
        """
        Update status for a completed transcript.
        """
        if self.val_token is None:
            self.val_tokengen()

        post_data = {
            'video_id': video_id,
            'name': name,
            'provider': provider,
            'language_code': lang_code,
            'file_format': transcript_format,
        }

        response = requests.post(
            self.auth_dict['val_transcript_create_url'],
            json=post_data,
            headers=self.headers,
            timeout=20
        )

        if not response.ok:
            LOGGER.error(
                '[API] : VAL update_val_transcript failed -- video_id=%s -- provider=% -- status=%s -- content=%s',
                video_id,
                provider,
                response.status_code,
                response.content,
            )

    def update_video_status(self, video_id, status):
        """
        Update video transcript status.
        """
        if self.val_token is None:
            self.val_tokengen()

        val_data = {
            'edx_video_id': video_id,
            'status': status
        }

        response = requests.patch(
            self.auth_dict['val_video_transcript_status_url'],
            json=val_data,
            headers=self.headers,
            timeout=20
        )

        if not response.ok:
            LOGGER.error(
                '[API] : VAL Update_video_status failed -- video_id=%s -- status=%s -- text=%s',
                video_id,
                response.status_code,
                response.text
            )
