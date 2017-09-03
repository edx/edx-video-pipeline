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
from django.db.models import Q
from pysrt import SubRipFile
from requests.packages.urllib3.exceptions import InsecurePlatformWarning
from rest_framework import status
from rest_framework.parsers import FormParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from control.veda_val import VALAPICall
from VEDA_OS01 import utils
from VEDA_OS01.models import (TranscriptCredentials, TranscriptProcessMetadata,
                              TranscriptProvider, TranscriptStatus,
                              VideoStatus)

requests.packages.urllib3.disable_warnings(InsecurePlatformWarning)

logging.basicConfig()
LOGGER = logging.getLogger(__name__)

# 3PlayMedia possible send-along statuses for a transcription callback.
COMPLETE = 'complete'
ERROR = 'error'

# Transcript format
TRANSCRIPT_SJSON = 'sjson'
CIELO24_TRANSCRIPT_COMPLETED = django.dispatch.Signal(providing_args=['job_id', 'lang_code', 'org', 'video_id'])
CIELO24_GET_CAPTION_URL = 'https://api.cielo24.com/api/job/get_caption'
CONFIG = utils.get_config()

# 3PlayMedia callback signal
THREE_PLAY_TRANSCRIPTION_DONE = django.dispatch.Signal(
    providing_args=['org', 'lang_code', 'edx_video_id', 'file_id', 'status', 'error_description']
)
# 3PlayMedia API URLs.
THREE_PLAY_TRANSCRIPT_URL = u'https://static.3playmedia.com/files/{file_id}/transcript.srt'
THREE_PLAY_TRANSLATION_SERVICES_URL = u'https://static.3playmedia.com/translation_services'
THREE_PLAY_ORDER_TRANSLATION_URL = u'https://api.3playmedia.com/files/{file_id}/translations/order'
THREE_PLAY_TRANSLATION_STATUS_URL = u'https://static.3playmedia.com/files/{file_id}/translations/{translation_id}'
THREE_PLAY_TRANSLATION_DOWNLOAD_URL = (u'https://static.3playmedia.com/files/{file_id}/translations/{translation_id}/'
                                       u'captions.srt')


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


class TranscriptTranslationError(TranscriptError):
    """
    An error occurred during the translation attempt on 3PlayMedia.
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
        required_attrs = ('job_id', 'lang_code', 'org', 'video_id')
        missing = [attr for attr in required_attrs if attr not in request.query_params.keys()]
        if missing:
            LOGGER.warning(
                '[CIELO24 HANDLER] Required params are missing %s',
                missing,
            )
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

    # get transcript credentials for an organization
    try:
        transcript_prefs = TranscriptCredentials.objects.get(
            org=org,
            provider=TranscriptProvider.CIELO24,
        )
    except TranscriptCredentials.DoesNotExist:
        LOGGER.exception('[CIELO24 TRANSCRIPTS] Unable to get transcript credentials for job_id=%s', job_id)

    # mark the transcript for a particular language as ready
    try:
        process_metadata = TranscriptProcessMetadata.objects.filter(
            provider=TranscriptProvider.CIELO24,
            process_id=job_id,
            lang_code=lang_code
        ).latest()
    except TranscriptProcessMetadata.DoesNotExist:
        LOGGER.exception(
            '[CIELO24 TRANSCRIPTS] Unable to get transcript process metadata for job_id=%s',
            job_id
        )

    # if transcript credentials are missing then we can do nothing
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
                '[CIELO24 TRANSCRIPTS] Request failed for video=%s -- lang=%s -- job_id=%s.',
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
    bucket = s3_conn.get_bucket(config['aws_video_transcripts_bucket'])
    k = Key(bucket)
    k.content_type = 'application/json'
    k.key = '{directory}{uuid}.sjson'.format(
        directory=config['aws_video_transcripts_prefix'],
        uuid=uuid.uuid4().hex
    )
    k.set_contents_from_string(json.dumps(sjson_data))
    return k.key


class ThreePlayMediaCallbackHandlerView(APIView):
    """
    View to handle 3PlayMedia callback requests.
    """
    parser_classes = (FormParser,)
    permission_classes = (AllowValidTranscriptProvider,)

    def post(self, request, **kwargs):
        """
        Handle 3PlayMedia callback request.
        """
        required_attrs = ['file_id', 'status', 'org', 'edx_video_id']
        received_attributes = request.data.keys() + request.query_params.keys()
        missing = [attr for attr in required_attrs if attr not in received_attributes]
        if missing:
            LOGGER.warning(
                u'[3PlayMedia Callback] process_id=%s Received Attributes=%s Missing Attributes=%s',
                request.data.get('file_id'),
                received_attributes,
                missing,
            )
            return Response(status=status.HTTP_200_OK)

        # Dispatch 3playMedia transcription signal
        THREE_PLAY_TRANSCRIPTION_DONE.send_robust(
            sender=self,
            org=request.query_params['org'],
            edx_video_id=request.query_params['edx_video_id'],
            lang_code='en',
            file_id=request.data['file_id'],
            status=request.data['status'],
            # Following is going to be an error description if an error occurs during
            # 3playMedia transcription process
            error_description=request.data.get('error_description'),
        )
        return Response(status=status.HTTP_200_OK)


def order_translations(file_id, api_key, api_secret, target_languages):
    """
    Order translations on 3PlayMedia for all the target languages.

    Process:
        * Fetch all the pending translations process for a file
        * Fetch all the translation services from 3PlayMedia
        * For each process,
            - Find suitable translation service
            - Order translation from that service
            - Move the process to `in progress` and update it with the
              translation id received from 3Play.

    Arguments:
        file_id(unicode): File identifier
        api_key(unicode): API key
        api_secret(unicode): API Secret
        target_languages(list): List of language codes

    Raises:
        TranscriptTranslationError: when an error occurred while fetching the translation services.
    """
    translation_processes = TranscriptProcessMetadata.objects.filter(
        process_id=file_id,
        provider=TranscriptProvider.THREE_PLAY,
        status=TranscriptStatus.PENDING,
        lang_code__in=target_languages,
    )

    response = requests.get(utils.build_url(THREE_PLAY_TRANSLATION_SERVICES_URL, apikey=api_key))
    if not response.ok:
        # Fail all the pending translation processes associated with this file id.
        translation_processes.update(status=TranscriptStatus.FAILED)

        raise TranscriptTranslationError(
            u'[3PlayMedia Callback] Error while fetching the translation services -- {status}, {response}'.format(
                status=response.status_code,
                response=response.text,
            )
        )

    # Response should be a list containing services, details:
    # http://support.3playmedia.com/hc/en-us/articles/227729988-Translations-API-Methods
    available_services = json.loads(response.text)
    if not isinstance(available_services, list):
        # Fail all the pending translation processes associated with this file id.
        translation_processes.update(status=TranscriptStatus.FAILED)

        raise TranscriptTranslationError(
            u'[3PlayMedia Callback] Expected list but got: -- {response}.'.format(
                response=response.text,
            )
        )

    for target_language in target_languages:
        try:
            translation_process = translation_processes.filter(lang_code=target_language).latest()
        except TranscriptProcessMetadata.DoesNotExist:
            LOGGER.warning(
                u'[3PlayMedia Callback] process not found for target language %s -- process id %s',
                target_language,
                file_id,
            )
            continue

        # 1 - Find a standard service for translation in the target language.
        translation_service_id = None
        for service in available_services:
            service_found = (
                service['target_language_iso_639_1_code'] == target_language and
                service['service_level'] == 'standard'
            )
            if service_found:
                translation_service_id = service['id']
                break

        if translation_service_id is None:
            # Fail the process
            translation_process.status = TranscriptStatus.FAILED
            translation_process.save()
            LOGGER.error(
                '[3PlayMedia Callback] No translation service found for target language %s -- process id %s',
                target_language,
                file_id,
            )
            continue

        # 2 - At this point, we've got our service ready to use. Now, place an order for the translation.
        response = requests.post(THREE_PLAY_ORDER_TRANSLATION_URL.format(file_id=file_id), json={
            'apikey': api_key,
            'api_secret_key': api_secret,
            'translation_service_id': translation_service_id,
        })

        if not response.ok:
            # Fail the process
            translation_process.status = TranscriptStatus.FAILED
            translation_process.save()
            LOGGER.error(
                '[3PlayMedia Callback] An error occurred during translation, target language=%s, file_id=%s, status=%s',
                target_language,
                file_id,
                response.status_code,
            )
            continue

        # Translation Order API returns `success` attribute specifying whether the order has been placed
        # successfully: http://support.3playmedia.com/hc/en-us/articles/227729988-Translations-API-Methods
        translation_order = json.loads(response.text)
        if translation_order.get('success'):
            translation_process.status = TranscriptStatus.IN_PROGRESS
            translation_process.translation_id = translation_order['translation_id']
            translation_process.save()
        else:
            translation_process.status = TranscriptStatus.FAILED
            translation_process.save()
            LOGGER.error(
                '[3PlayMedia Callback] Translation failed fot target language=%s, file_id=%s, response=%s',
                target_language,
                file_id,
                response.text,
            )


@django.dispatch.receiver(THREE_PLAY_TRANSCRIPTION_DONE, dispatch_uid="three_play_transcription_done")
def three_play_transcription_callback(sender, **kwargs):
    """
    This is a receiver for 3Play Media callback signal.

    Arguments:
        sender: sender of the signal
        kwargs(dict): video transcription metadata

    Process:
        * download transcript(SRT) from 3PlayMedia
        * convert SRT to SJSON
        * upload SJSON to AWS S3
        * order translations for all the preferred languages
        * update transcript status in VAL
    """
    # Extract all the must have attributes
    org = kwargs['org']
    edx_video_id = kwargs['edx_video_id']
    lang_code = kwargs['lang_code']
    file_id = kwargs['file_id']
    state = kwargs['status']

    try:
        process = TranscriptProcessMetadata.objects.filter(
            provider=TranscriptProvider.THREE_PLAY,
            process_id=file_id,
            lang_code=lang_code,
        ).latest()
    except TranscriptProcessMetadata.DoesNotExist:
        LOGGER.exception(
            u'[3PlayMedia Callback] Unable to get transcript process for org=%s, edx_video_id=%s, file_id=%s.',
            org,
            edx_video_id,
            file_id,
        )
        return

    if state == COMPLETE:
        # Indicates that the default video speech transcription has been done successfully.
        try:
            transcript_secrets = TranscriptCredentials.objects.get(org=org, provider=TranscriptProvider.THREE_PLAY)
        except TranscriptCredentials.DoesNotExist:
            # Fail the process
            process.status = TranscriptStatus.FAILED
            process.save()
            # Log the failure
            LOGGER.exception(
                u'[3PlayMedia Callback] Unable to get transcript secrets for org=%s, edx_video_id=%s, file_id=%s.',
                org,
                edx_video_id,
                file_id,
            )
            return

        # Fetch the transcript from 3PlayMedia
        try:
            srt_transcript = fetch_srt_data(
                THREE_PLAY_TRANSCRIPT_URL.format(file_id=file_id),
                apikey=transcript_secrets.api_key,
            )
        except TranscriptFetchError:
            process.status = TranscriptStatus.FAILED
            process.save()
            LOGGER.exception(
                '[3PlayMedia Callback] Fetch request failed for video=%s -- lang=%s -- process_id=%s',
                edx_video_id,
                lang_code,
                file_id
            )
            return

        # fetched transcript is going to be SRT content and if this is not so, it'll be a json response
        # describing the error.
        try:
            json.loads(srt_transcript)
            # Fail the process and log all the details.
            process.status = TranscriptStatus.FAILED
            process.save()
            LOGGER.error(
                '[3PlayMedia Task] Transcript fetch error for video=%s -- lang_code=%s -- process=%s -- response=%s',
                process.video.studio_id,
                process.lang_code,
                process.process_id,
                srt_transcript,
            )
            return
        except ValueError:
            pass

        # We've got the transcript from 3PlayMedia, now update process status accordingly.
        process.status = TranscriptStatus.READY
        process.save()

        try:
            sjson_transcript = convert_srt_to_sjson(srt_transcript)
            sjson_file = upload_sjson_to_s3(CONFIG, sjson_transcript)
        except Exception:
            # in case of any exception, log and raise.
            LOGGER.exception(
                u'[3PlayMedia Callback] Request failed for video=%s -- lang_code=%s -- process_id=%s',
                edx_video_id,
                lang_code,
                file_id,
            )
            raise

        # Update edx-val with completed transcript information
        val_api = VALAPICall(video_proto=None, val_status=None)
        val_api.update_val_transcript(
            video_id=process.video.studio_id,
            lang_code=lang_code,
            name=sjson_file,
            transcript_format=TRANSCRIPT_SJSON,
            provider=TranscriptProvider.THREE_PLAY,
        )

        # Translation Phase
        target_languages = list(process.video.preferred_languages)
        # Remove the language that is already processed - in our case, its en.
        target_languages.remove(lang_code)

        # Check if the translations are needed.
        if target_languages:
            # Create the translation tracking processes for all the target languages.
            for target_language in target_languages:
                TranscriptProcessMetadata.objects.create(
                    video=process.video,
                    provider=TranscriptProvider.THREE_PLAY,
                    process_id=file_id,
                    lang_code=target_language,
                    status=TranscriptStatus.PENDING,
                )

            try:
                # Order translations for target languages
                order_translations(file_id, transcript_secrets.api_key, transcript_secrets.api_secret, target_languages)
            except TranscriptTranslationError:
                LOGGER.exception(
                    u'[3PlayMedia Callback] Translation could not be performed - org=%s, edx_video_id=%s, file_id=%s.',
                    org,
                    edx_video_id,
                    file_id,
                )
            except Exception:
                LOGGER.exception(
                    (u'[3PlayMedia Callback] Error while translating the transcripts - org=%s, edx_video_id=%s, '
                     u'file_id=%s.'),
                    org,
                    edx_video_id,
                    file_id,
                )
                raise

        # in case if there is only one language which has already been processed.
        if not target_languages:
            val_api.update_video_status(
                process.video.studio_id, VideoStatus.TRANSCRIPTION_READY
            )

        # On success, a happy farewell log.
        LOGGER.info(
            u'[3PlayMedia Callback] Video speech transcription was successful for video=%s -- lang_code=%s -- '
            u'process_id=%s',
            edx_video_id,
            lang_code,
            file_id,
        )

    elif state == ERROR:
        # Fail the process
        process.status = TranscriptStatus.FAILED
        process.save()
        # Log the error information
        LOGGER.error(
            u'[3PlayMedia Callback] Error while transcription - error=%s, org=%s, edx_video_id=%s, file_id=%s.',
            kwargs['error_description'],
            org,
            edx_video_id,
            file_id,
        )
    else:
        # Status must be either 'complete' or 'error'
        # more details on http://support.3playmedia.com/hc/en-us/articles/227729828-Files-API-Methods
        LOGGER.error(
            u'[3PlayMedia Callback] Got invalid status - status=%s, org=%s, edx_video_id=%s, file_id=%s.',
            state,
            org,
            edx_video_id,
            file_id,
        )


def retrieve_three_play_translations():
    """
    Checks translation status on 3PlayMedia for all the progressing processes, fetches them if they're complete.

    Retrieval flow:
    1. Fetches 3PlayMedia translation processes whose status is `in progress`
    2. For each process, retrieve the org-wide api keys
    3. Check translation status through 3PlayMedia
    4. If its done, mark the process as complete, fetch translated transcript, convert to sjson, upload it to s3 and
    finally, update it in edx-val.
    """

    translation_processes = TranscriptProcessMetadata.objects.filter(
        provider=TranscriptProvider.THREE_PLAY,
        status=TranscriptStatus.IN_PROGRESS,
    ).exclude(Q(translation_id__isnull=True) | Q(translation_id__exact=''))

    for translation_process in translation_processes:
        course_id = translation_process.video.inst_class.local_storedir.split(',')[0]
        org = utils.extract_course_org(course_id=course_id)

        try:
            three_play_secrets = TranscriptCredentials.objects.get(org=org, provider=TranscriptProvider.THREE_PLAY)
        except TranscriptCredentials.DoesNotExist:
            LOGGER.exception(
                u'[3PlayMedia Task] 3Play secrets not found for video=%s -- lang_code=%s -- process_id=%s',
                translation_process.video.studio_id,
                translation_process.lang_code,
                translation_process.process_id,
            )
            continue

        translation_status_url = utils.build_url(
            THREE_PLAY_TRANSLATION_STATUS_URL.format(
                file_id=translation_process.process_id,
                translation_id=translation_process.translation_id,
            ),
            apikey=three_play_secrets.api_key
        )
        response = requests.get(translation_status_url)
        if not response.ok:
            LOGGER.error(
                (u'[3PlayMedia Task] Translation status request failed for video=%s -- '
                 u'lang_code=%s -- process_id=%s -- status=%s'),
                translation_process.video.studio_id,
                translation_process.lang_code,
                translation_process.process_id,
                response.status_code,
            )
            continue

        translation_status = json.loads(response.text)
        if translation_status.get('iserror'):
            translation_process.status = TranscriptStatus.FAILED
            translation_process.save()
            LOGGER.error(
                (u'[3PlayMedia Task] unable to get translation status for video=%s -- '
                 u'lang_code=%s -- process_id=%s -- response=%s'),
                translation_process.video.studio_id,
                translation_process.lang_code,
                translation_process.process_id,
                response.text,
            )
            continue

        if translation_status['state'] == 'complete':
            try:
                response = fetch_srt_data(
                    url=THREE_PLAY_TRANSLATION_DOWNLOAD_URL.format(
                        file_id=translation_process.process_id, translation_id=translation_process.translation_id
                    ),
                    apikey=three_play_secrets.api_key,
                )
            except TranscriptFetchError:
                LOGGER.exception(
                    u'[3PlayMedia Task] Translation download failed for video=%s -- lang_code=%s -- process_id=%s.',
                    translation_process.video.studio_id,
                    translation_process.lang_code,
                    translation_process.process_id
                )
                continue

            # its going to be SRT content and `json.loads` should raise
            # ValueError if its a valid response, otherwise it'll be json
            # response in result of an error.
            try:
                json.loads(response)
                translation_process.status = TranscriptStatus.FAILED
                translation_process.save()
                LOGGER.error(
                    u'[3PlayMedia Task] Translation error for video=%s -- lang_code=%s -- process_id=%s -- response=%s',
                    translation_process.video.studio_id,
                    translation_process.lang_code,
                    translation_process.process_id,
                    response.text,
                )
                continue
            except ValueError:
                pass

            # We've got the transcript from 3PlayMedia, now update process status accordingly.
            translation_process.status = TranscriptStatus.READY
            translation_process.save()

            try:
                sjson_transcript = convert_srt_to_sjson(response)
                sjson_file = upload_sjson_to_s3(CONFIG, sjson_transcript)
            except Exception:
                # in case of any exception, log and raise.
                LOGGER.exception(
                    u'[3PlayMedia Task] translation failed for video=%s -- lang_code=%s -- process_id=%s',
                    translation_process.video.studio_id,
                    translation_process.lang_code,
                    translation_process.process_id,
                )
                raise

            # Update edx-val with completed transcript information
            val_api = VALAPICall(video_proto=None, val_status=None)
            val_api.update_val_transcript(
                video_id=translation_process.video.studio_id,
                lang_code=translation_process.lang_code,
                name=sjson_file,
                transcript_format=TRANSCRIPT_SJSON,
                provider=TranscriptProvider.THREE_PLAY,
            )

            # if all the processes for this video are complete, update video status in edx-val
            # update transcript status for video in edx-val only if all language transcripts are ready
            video_jobs = TranscriptProcessMetadata.objects.filter(video__studio_id=translation_process.video.studio_id)
            if all(video_job.status == TranscriptStatus.READY for video_job in video_jobs):
                val_api.update_video_status(translation_process.video.studio_id, VideoStatus.TRANSCRIPTION_READY)
