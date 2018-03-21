"""
Cielo24 API Job Start and Download
Options (reflected in Course.models):
transcription_fidelity =
  Mechanical (75%),
  Premium (95%)(3-72h),
  Professional (99+%)(3-72h)
priority =
  standard (24h),
  priority (48h)
turnaround_hours = number, overrides 'priority' call, will change a standard to a priority silently
"""
import logging
import requests
import ast
import urllib

from control_env import *

requests.packages.urllib3.disable_warnings()
LOGGER = logging.getLogger(__name__)
# TODO: Remove this temporary logging to stdout
logging.basicConfig(stream=sys.stdout, level=logging.INFO)


class Cielo24TranscriptOld(object):

    def __init__(self, veda_id):
        self.veda_id = veda_id
        '''Defaults'''
        self.c24_site = 'https://api.cielo24.com/api'
        self.c24_login = '/account/login'
        self.c24_joblist = '/job/list'
        self.c24_newjob = '/job/new'
        self.add_media = '/job/add_media'
        self.transcribe = '/job/perform_transcription'

        '''Retreive C24 Course-based defaults'''
        self.c24_defaults = self.retrieve_defaults()

    def perform_transcription(self):
        if self.c24_defaults['c24_user'] is None:
            return None
        '''
        GET /api/job/perform_transcription?v=1 HTTP/1.1
        &api_token=xxxx
        &job_id=xxxx
        &transcription_fidelity=PREMIUM&priority=STANDARD
        Host: api.cielo24.com
        '''
        api_token = self.tokengenerator()
        if api_token is None:
            return None

        job_id = self.generate_jobs(api_token)
        task_id = self.embed_url(api_token, job_id)

        r5 = requests.get(
            ''.join((
                self.c24_site,
                self.transcribe,
                '?v=1&api_token=',
                api_token,
                '&job_id=',
                job_id,
                '&transcription_fidelity=',
                self.c24_defaults['c24_fidelity'],
                '&priority=',
                self.c24_defaults['c24_speed']
            ))
        )
        return ast.literal_eval(r5.text)['TaskId']

    def retrieve_defaults(self):
        video_query = Video.objects.filter(
            edx_id=self.veda_id
        ).latest()

        url_query = URL.objects.filter(
            videoID=video_query,
            encode_url__icontains='_DTH.mp4',
        ).latest()

        if video_query.inst_class.c24_username is None:
            LOGGER.error('[VIDEO_PIPELINE] {id} : Cielo API : Course record incomplete'.format(id=self.veda_id))
            return None

        c24_defaults = {
            'c24_user': video_query.inst_class.c24_username,
            'c24_pass': video_query.inst_class.c24_password,
            'c24_speed': video_query.inst_class.c24_speed,
            'c24_fidelity': video_query.inst_class.c24_fidelity,
            'edx_id': self.veda_id,
            'url': url_query.encode_url
        }
        return c24_defaults

    def tokengenerator(self):
        token_url = self.c24_site + self.c24_login + \
            '?v=1&username=' + self.c24_defaults['c24_user'] + \
            '&password=' + self.c24_defaults['c24_pass']

        # Generate Token
        r1 = requests.get(token_url)
        if r1.status_code > 299:
            LOGGER.error('[VIDEO_PIPELINE] {id} : Cielo API access'.format(id=self.veda_id))
            return
        api_token = ast.literal_eval(r1.text)["ApiToken"]
        return api_token

    def listjobs(self):
        """List Jobs"""
        api_token = self.tokengenerator()
        r2 = requests.get(
            ''.join((
                self.c24_site,
                self.c24_joblist,
                '?v=1&api_token=',
                api_token
            ))
        )
        job_list = r2.text
        return job_list

    def generate_jobs(self, api_token):
        """
        'https://api.cielo24.com/job/new?v=1&\
        api_token=xxx&job_name=xxx&language=en'
        """
        r3 = requests.get(
            ''.join((
                self.c24_site,
                self.c24_newjob,
                '?v=1&api_token=',
                api_token,
                '&job_name=',
                self.c24_defaults['edx_id'],
                '&language=en'
            ))
        )
        job_id = ast.literal_eval(r3.text)['JobId']
        return job_id

    def embed_url(self, api_token, job_id):
        """
        GET /api/job/add_media?v=1&api_token=xxxx
        &job_id=xxxxx
        &media_url=http%3A%2F%2Fwww.domain.com%2Fvideo.mp4 HTTP/1.1
        Host: api.cielo24.com
        """
        r4 = requests.get(
            ''.join((
                self.c24_site,
                self.add_media,
                '?v=1&api_token=',
                api_token,
                '&job_id=',
                job_id,
                '&media_url=',
                urllib.quote_plus(self.c24_defaults['url'])
            ))
        )
        return ast.literal_eval(r4.text)['TaskId']


def main():
    pass


if __name__ == "__main__":
    sys.exit(main())
