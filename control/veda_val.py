
import os
import sys
import requests
import ast
import json
import datetime
import yaml
import newrelic.agent

requests.packages.urllib3.disable_warnings()

newrelic.agent.initialize(
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'veda_newrelic.ini'
    )
)

"""
Send data to VAL, either Video ID data or endpoint URLs

"""

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
from control_env import *
from control.veda_utils import ErrorObject, Output


class VALAPICall():

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
        self.auth_yaml = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'instance_config.yaml'
        )
        self.auth_dict = self._AUTH()

    @newrelic.agent.background_task()
    def call(self):
        if self.auth_dict is None:
            print 'No AUTH'
            return None

        """
        Errors covered in other methods
        """
        if self.val_token is None:
            self.val_tokengen()
        if self.video_object is not None:
            print 'VIDEO OBJECT'
            self.send_object_data()
        if self.video_proto is not None:
            print 'VIDEO PROTO'
            self.send_val_data()

    def _AUTH(self):
        if not os.path.exists(self.auth_yaml):
            ErrorObject.print_error(
                message='No Auth YAML'
            )
            return None

        with open(self.auth_yaml, 'r') as stream:
            try:
                auth_dict = yaml.load(stream)
                return auth_dict
            except yaml.YAMLError as exc:
                ErrorObject.print_error(
                    message='YAML READ ERROR'
                )
                return None

    @newrelic.agent.background_task()
    def val_tokengen(self):

        payload = {
            'grant_type': 'password',
            'client_id': self.auth_dict['val_client_id'],
            'client_secret': self.auth_dict['val_secret_key'],
            'username': self.auth_dict['val_username'],
            'password': self.auth_dict['val_password'],
        }

        r = requests.post(self.auth_dict['val_token_url'], data=payload, timeout=20)

        if r.status_code != 200:
            ErrorObject.print_error(
                message='Token Gen Fail: VAL\nCheck VAL Config'
            )
            return None

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
        class VideoProto():
            platform_course_url = []

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
        if self.val_token is None:
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

        if not isinstance(self.video_proto.duration, float):
            self.video_proto.duration = Output._seconds_from_string(
                duration=self.video_object.video_orig_duration
            )

        """
        Sort out courses
        """
        val_courses = []
        if self.val_status != 'invalid_token':
            for f in self.video_object.inst_class.local_storedir.split(','):
                if f.strip() not in val_courses:
                    val_courses.append({f.strip(): None})

        if len(val_courses) == 0:
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
            timeout=20
        )

        if r1.status_code != 200 and r1.status_code != 404:
            ErrorObject.print_error(
                message='R1 : VAL Communication Fail: VAL\nCheck VAL Config'
            )
            return None

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
        if self.endpoint_url is not None:
            for p in self.auth_dict['val_profile_dict'][self.encode_profile]:

                self.encode_data.append(dict(
                    url=self.endpoint_url,
                    file_size=self.video_proto.filesize,
                    bitrate=int(self.video_proto.bitrate.split(' ')[0]),
                    profile=p
                ))

        test_list = []
        if self.video_proto.veda_id is not None:
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
            return None

        """
        All URL Records Deleted (for some reason)
        """
        if len(self.encode_data) == 0:
            return None

        for i in val_api_return['encoded_videos']:
            if i['profile'] not in [g['profile'] for g in self.encode_data]:
                self.encode_data.append(i)

        return None

    def send_404(self):
        """
        Generate new VAL ID
        """
        self.profile_determiner(val_api_return=[])

        self.val_data['status'] = self.val_status

        if len(self.encode_data) == 0 and self.val_status is 'file_complete':
            return None

        sending_data = dict(
            encoded_videos=self.encode_data,
            **self.val_data
        )

        r2 = requests.post(
            self.auth_dict['val_api_url'] + '/',
            data=json.dumps(sending_data),
            headers=self.headers,
            timeout=20
        )

        if r2.status_code > 299:
            ErrorObject.print_error(
                message='%s\n %s\n %s\n' % (
                    'R2 : VAL POST/PUT Fail: VAL',
                    'Check VAL Config',
                    r2.status_code
                )
            )

    def send_200(self, val_api_return):
        """
        VAL ID is previously extant
        just update
        ---
        VAL will not allow duped studio urls to be sent,
        so we must scrub the data
        """
        for course in val_api_return['courses']:
            for course_id in course.keys():
                for course_entry in self.val_data['courses']:
                    if course_id in course_entry:
                        self.val_data['courses'].remove(course_entry)

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
        if len(self.encode_data) == 0 and self.val_status is 'file_complete':
            return None

        r4 = requests.put(
            '/'.join((
                self.auth_dict['val_api_url'],
                self.video_proto.val_id,
            )),
            data=json.dumps(sending_data),
            headers=self.headers,
            timeout=20
        )

        if r4.status_code > 299:
            ErrorObject.print_error(
                message='%s\n %s\n %s\n' % (
                    'R4 : VAL POST/PUT Fail: VAL',
                    'Check VAL Config',
                    r4.status_code
                )
            )


def main():
    pass


if __name__ == '__main__':
    sys.exit(main())
