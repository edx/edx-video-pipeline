"""
Transcript handlers.
"""
import json
import logging
import uuid

import boto
import django.dispatch
import requests
from boto.s3.key import Key
from pysrt import SubRipFile
from requests.packages.urllib3.exceptions import InsecurePlatformWarning
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from control.veda_val import VALAPICall
from VEDA_OS01 import utils
from VEDA_OS01.models import (TranscriptPreferences, TranscriptProcessMetadata,
                              TranscriptProvider, TranscriptStatus,
                              VideoStatus)

requests.packages.urllib3.disable_warnings(InsecurePlatformWarning)

LOGGER = logging.getLogger(__name__)
TRANSCRIPT_SJSON = 'sjson'
CIELO24_TRANSCRIPT_COMPLETED = django.dispatch.Signal(providing_args=['job_id', 'lang_code', 'org', 'video_id'])
CIELO24_GET_CAPTION_URL = 'https://api.cielo24.com/api/job/get_caption'
CONFIG = utils.get_config()


class TranscriptError(Exception):
    """
    An error occurred during fetching transcript from cielo24.
    """
    pass


class TranscriptFetchError(TranscriptError):
    """
    An error occurred during fetching transcript from cielo24.
    """
    pass


class TranscriptConversionError(TranscriptError):
    """
    An error occurred during srt to sjson conversion.
    """
    pass


class TranscriptUploadError(TranscriptError):
    """
    An error occurred during sjson upload to s3.
    """
    pass


class AllowValidTranscriptProvider(AllowAny):
    """
    Permission class to allow only valid transcript provider.
    """
    def has_permission(self, request, view):
        """
        Check if request is from valid transcript provider.
        """
        try:
            return CONFIG['transcript_provider_request_token'] == view.kwargs['token']
        except KeyError:
            return False


class Cielo24CallbackHandlerView(APIView):
    """
    View to handler Cielo24 callback requests.
    """
    permission_classes = (AllowValidTranscriptProvider,)

    def get(self, request, **kwargs):
        """
        Handle Cielo24 callback request.
        """
        attrs = ('job_id', 'lang_code', 'org', 'video_id')
        if not all([attr in request.query_params for attr in attrs]):
            LOGGER.warn('[CIELO24 HANDLER] Required params are missing %s', request.query_params.keys())
            return Response({}, status=status.HTTP_400_BAD_REQUEST)

        CIELO24_TRANSCRIPT_COMPLETED.send_robust(
            sender=self,
            org=request.query_params['org'],
            job_id=request.query_params['job_id'],
            video_id=request.query_params['video_id'],
            lang_code=request.query_params['lang_code'],
        )
        return Response()


@django.dispatch.receiver(CIELO24_TRANSCRIPT_COMPLETED, dispatch_uid="cielo24_transcript_completed")
def cielo24_transcript_callback(sender, **kwargs):
    """
    * download transcript(SRT) from Cielo24
    * convert SRT to SJSON
    * upload SJSON to AWS S3
    * update transcript status in VAL
    """
    process_metadata = None
    transcript_prefs = None

    org = kwargs['org']
    job_id = kwargs['job_id']
    video_id = kwargs['video_id']
    lang_code = kwargs['lang_code']

    LOGGER.info(
        '[CIELO24 TRANSCRIPTS] Transcript complete request received for video=%s -- org=%s -- lang=%s -- job_id=%s',
        video_id,
        org,
        lang_code,
        job_id
    )

    # get transcript preferences for an organization
    try:
        transcript_prefs = TranscriptPreferences.objects.get(
            org=org,
            provider=TranscriptProvider.CIELO24,
        )
    except TranscriptPreferences.DoesNotExist:
        LOGGER.exception('[CIELO24 TRANSCRIPTS] Unable to get transcript preferences for job_id=%s', job_id)

    # mark the transcript for a particular language as ready
    try:
        process_metadata = TranscriptProcessMetadata.objects.filter(
            provider=TranscriptProvider.CIELO24,
            process_id=job_id,
            lang_code=lang_code
        ).latest('modified')
    except TranscriptProcessMetadata.DoesNotExist:
        LOGGER.exception(
            '[CIELO24 TRANSCRIPTS] Unable to get transcript process metadata for job_id=%s',
            job_id
        )

    # if transcript preferences are missing then we can do nothing
    if not transcript_prefs and process_metadata:
        process_metadata.status = TranscriptStatus.FAILED
        process_metadata.save()

    if transcript_prefs and process_metadata:
        api_key = transcript_prefs.api_key
        try:
            srt_data = fetch_srt_data(
                CIELO24_GET_CAPTION_URL,
                v=1,
                job_id=job_id,
                api_token=api_key,
                caption_format='SRT'
            )
        except TranscriptFetchError:
            process_metadata.status = TranscriptStatus.FAILED
            process_metadata.save()
            LOGGER.exception(
                '[CIELO24 TRANSCRIPTS] Fetch request failed for video=%s -- lang=%s -- job_id=%s',
                video_id,
                lang_code,
                job_id
            )
            return

        process_metadata.status = TranscriptStatus.READY
        process_metadata.save()

        try:
            sjson = convert_srt_to_sjson(srt_data)
            sjson_file_name = upload_sjson_to_s3(CONFIG, sjson)
        except Exception:
            LOGGER.exception(
                '[CIELO24 TRANSCRIPTS] Request failed for video=%s -- lang=%s -- job_id=%s -- message=%s',
                video_id,
                lang_code,
                job_id
            )
            raise

        # update edx-val with completed transcript information
        val_api = VALAPICall(process_metadata.video, val_status=None)
        val_api.update_val_transcript(
            video_id=process_metadata.video.studio_id,
            lang_code=lang_code,
            name=sjson_file_name,
            transcript_format=TRANSCRIPT_SJSON,
            provider=TranscriptProvider.CIELO24
        )

        # update transcript status for video in edx-val only if all langauge transcripts are ready
        video_jobs = TranscriptProcessMetadata.objects.filter(video__studio_id=video_id)
        if all(video_job.status == TranscriptStatus.READY for video_job in video_jobs):
            val_api.update_video_status(process_metadata.video.studio_id, VideoStatus.TRANSCRIPTION_READY)


def fetch_srt_data(url, **request_params):
    """
    Fetch srt data from transcript provider.
    """
    # return TRANSCRIPT_SRT_DATA
    response = requests.get(
        utils.build_url(url, **request_params)
    )

    if not response.ok:
        raise TranscriptFetchError(
            '[TRANSCRIPT FETCH ERROR] status={} -- text={}'.format(
                response.status_code,
                response.text
            )
        )

    return response.text


def convert_srt_to_sjson(srt_data):
    """
    Convert SRT to SJSON

    Arguments:
        srt_data: unicode, content of source subs.

    Returns:
        dict: SJSON data
    """
    srt_subs_obj = SubRipFile.from_string(srt_data)

    sub_starts = []
    sub_ends = []
    sub_texts = []

    for sub in srt_subs_obj:
        sub_starts.append(sub.start.ordinal)
        sub_ends.append(sub.end.ordinal)
        sub_texts.append(sub.text.replace('\n', ' '))

    subs = {
        'start': sub_starts,
        'end': sub_ends,
        'text': sub_texts
    }

    return subs


def upload_sjson_to_s3(config, sjson_data):
    """
    Upload sjson data to s3.
    """
    s3_conn = boto.connect_s3()
    bucket = s3_conn.get_bucket(config['transcript_bucket_name'])
    k = Key(bucket)
    k.content_type = 'application/json'
    k.key = '{directory}{uuid}.sjson'.format(
        directory=config['transcript_bucket_directory'],
        uuid=uuid.uuid4().hex
    )
    k.set_contents_from_string(json.dumps(sjson_data))
    return k.key
