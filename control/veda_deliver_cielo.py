"""
Cielo24 Integration
"""

import ast
import logging
import json

import requests
import urllib3

from VEDA_OS01.models import (TranscriptProcessMetadata, TranscriptProvider,
                              TranscriptStatus)
from VEDA.utils import build_url, scrub_query_params
from VEDA_OS01.transcripts import CIELO24_API_VERSION

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

LOGGER = logging.getLogger(__name__)


class Cielo24Error(Exception):
    """
    An error that occurs during cielo24 actions.
    """
    pass


class Cielo24CreateJobError(Cielo24Error):
    """
    An error occurred during new job creation.
    """
    pass


class Cielo24AddMediaError(Cielo24Error):
    """
    An error occurred during add media.
    """
    pass


class Cielo24PerformTranscriptError(Cielo24Error):
    """
    An error occurred during perform transcript.
    """
    pass


class Cielo24Transcript(object):
    """
    Cielo24 Integration
    """
    def __init__(
            self,
            video,
            org,
            api_key,
            turnaround,
            fidelity,
            preferred_languages,
            s3_video_url,
            callback_base_url,
            cielo24_api_base_url
    ):
        self.org = org
        self.video = video
        self.api_key = api_key
        self.fidelity = fidelity
        self.turnaround = turnaround
        self.preferred_languages = preferred_languages
        self.s3_video_url = s3_video_url
        self.callback_base_url = callback_base_url

        # Defaults
        self.cielo24_api_base_url = cielo24_api_base_url
        self.cielo24_new_job = '/job/new'
        self.cielo24_add_media = '/job/add_media'
        self.cielo24_perform_transcription = '/job/perform_transcription'

    def start_transcription_flow(self):
        """
        Start cielo24 transcription flow.

        This will do the following steps:
        For each preferred language:
            1. create a new job
            2. add media url
            3. perform transcript
        """
        job_id = None

        for preferred_lang in self.preferred_languages:
            try:
                job_id = self.create_job()
                transcript_process_metadata = TranscriptProcessMetadata.objects.create(
                    video=self.video,
                    process_id=job_id,
                    lang_code=preferred_lang,
                    provider=TranscriptProvider.CIELO24,
                    status=TranscriptStatus.IN_PROGRESS
                )
                self.embed_media_url(job_id)
                self.perform_transcript(job_id, preferred_lang)
            except Cielo24Error as ex:
                if job_id:
                    transcript_process_metadata.status = TranscriptStatus.FAILED
                    transcript_process_metadata.save()

                LOGGER.exception(
                    '[CIELO24] Request failed for video=%s -- lang=%s -- job_id=%s',
                    self.video.studio_id,
                    preferred_lang,
                    job_id
                )

    def perform_transcript(self, job_id, lang_code):
        """
        Request cielo24 to generate transcripts for a video.
        """
        callback_url = '{}?job_id={}&iwp_name={}&lang_code={}&org={}&video_id={}'.format(
            self.callback_base_url,
            job_id,
            '{iwp_name}',
            lang_code,
            self.org,
            self.video.studio_id
        )

        perform_transcript_url = build_url(
            self.cielo24_api_base_url,
            self.cielo24_perform_transcription,
            v=CIELO24_API_VERSION,
            job_id=job_id,
            target_language=lang_code,
            callback_url=callback_url,
            api_token=self.api_key,
            priority=self.turnaround,
            transcription_fidelity=self.fidelity,
            options=json.dumps({"return_iwp":["FINAL"]})
        )
        response = requests.get(perform_transcript_url)

        if not response.ok:
            raise Cielo24PerformTranscriptError(
                '[PERFORM TRANSCRIPT ERROR] url={} -- status={} -- text={}'.format(
                    scrub_query_params(perform_transcript_url, ['api_token']),
                    response.status_code,
                    response.text
                )
            )

        task_id = ast.literal_eval(response.text)['TaskId']
        LOGGER.info(
            '[CIELO24] Perform transcript request successful for video=%s with job_id=%s and task_id=%s',
            self.video.studio_id,
            job_id,
            task_id
        )
        return job_id

    def embed_media_url(self, job_id):
        """
        Create cielo24 add media url.

        Arguments:
            job_id (str): cielo24 job id

        Returns:
            cielo24 task id
        """
        media_url = build_url(
            self.cielo24_api_base_url,
            self.cielo24_add_media,
            v=CIELO24_API_VERSION,
            job_id=job_id,
            api_token=self.api_key,
            media_url=self.s3_video_url
        )
        response = requests.get(media_url)

        if not response.ok:
            raise Cielo24AddMediaError(
                '[ADD MEDIA ERROR] url={} -- status={} -- text={}'.format(
                    scrub_query_params(media_url, ['api_token']),
                    response.status_code,
                    response.text
                )
            )

        task_id = ast.literal_eval(response.text)['TaskId']
        LOGGER.info(
            '[CIELO24] Media url created for video=%s with job_id=%s and task_id=%s',
            self.video.studio_id,
            job_id,
            task_id
        )
        return task_id

    def create_job(self):
        """
        Create new job for transcription.

        Returns:
            cielo24 job id
        """
        create_job_url = build_url(
            self.cielo24_api_base_url,
            self.cielo24_new_job,
            v=CIELO24_API_VERSION,
            language=self.video.source_language,
            api_token=self.api_key,
            job_name=self.video.studio_id
        )
        response = requests.get(create_job_url)

        if not response.ok:
            raise Cielo24CreateJobError(
                '[CREATE JOB ERROR] url={} -- status={} -- text={}'.format(
                    scrub_query_params(create_job_url, ['api_token']),
                    response.status_code,
                    response.text,
                )
            )

        job_id = ast.literal_eval(response.text)['JobId']
        LOGGER.info(
            '[CIELO24] New job created for video=%s with job_id=%s',
            self.video.studio_id,
            job_id
        )
        return job_id
