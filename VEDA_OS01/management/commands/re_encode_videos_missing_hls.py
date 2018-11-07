"""
Management command used to re-ingest video from hotstore based on the params provided.

 - Request edxval for set of videos to re-encode
 - Retrieve corresponding VEDA Video object and switch off process_transcription flag This is required to avoid unintentional transcription that happens in Delivery phase.
 - Check VEDA to see whether an HLS profile is there and if it does then, just update edxval with it otherwise kick off encoding task (a.k.a worker_tasks_fire) with veda_id and encode_profile=HLS.
 - Encode worker generates the HLS encode, push it S3 and initiate a delivery task
 - Deliver worker process the delivery task and delivers the successful HLS encode profile to edxval

"""
import ast
import logging
import uuid

import requests
from django.core.management.base import BaseCommand

from VEDA_OS01.models import Video, EncodeVideosMissingHlsConfiguration, URL, Encode
from VEDA.utils import get_config
from control import celeryapp

LOGGER = logging.getLogger(__name__)


def get_auth_token(settings):
    """
    Generate a API token for VAL
    """
    token = None
    payload = {
        'grant_type': 'password',
        'client_id': settings['val_client_id'],
        'client_secret': settings['val_secret_key'],
        'username': settings['val_username'],
        'password': settings['val_password'],
    }
    response = requests.post(
        settings['val_token_url'],
        data=payload,
        timeout=settings['global_timeout']
    )

    if response.status_code == 200:
        token = ast.literal_eval(response.text)['access_token']
    else:
        LOGGER.error('EDXVAL Token Generation Error: %s', response.text)

    return token


def get_videos_wo_hls(courses=None, batch_size=None, offset=None):
    """
    Get videos from edxval which are missing HLS profiles.

    Arguments:
        courses: List of course IDs
        batch_size: Number of videos per batch
        offset: Position to pick the batch of videos
    """
    settings = get_config()
    token = get_auth_token(settings)
    if not token:
        return

    # Build request headers and query parameters.
    headers = {
        'Authorization': 'Bearer {token}'.format(token=token),
        'content-type': 'application/json'
    }

    if courses:
        params = {
            'courses': courses
        }
    else:
        params = {
            'batch_size': batch_size,
            'offset': offset
        }

    # Make request to edxval for videos
    val_videos_url = '/'.join([settings['val_api_url'], 'missing-hls/'])
    response = requests.get(
        val_videos_url, params=params, headers=headers
    )

    videos = None
    if response.status_code == 200:
        response = response.json()
        videos = response['videos']
        if courses:
            videos_done = 0
            videos_in_progress = videos_total = len(videos)
        else:
            videos_done = response['total'] - response['offset']
            videos_in_progress = response['batch_size']
            videos_total = response['total']

        LOGGER.info(
            u"videos(in-progress)=%s - videos(done)=%s - videos(total)=%s",
            videos_in_progress,
            videos_done,
            videos_total,
        )
    else:
        LOGGER.error(
            u"Error while getting Videos for re-encode: %s",
            response.text,
        )

    return videos


def enqueue_video_for_hls_encode(veda_id, encode_queue):
    task_result = celeryapp.worker_task_fire.apply_async(
        (veda_id, 'hls', uuid.uuid1().hex[0:10]),
        queue=encode_queue.strip(),
        connect_timeout=3
    )
    # Mis-queued Task
    if task_result == 1:
        LOGGER.error('[ENQUEUE] {veda_id} queueing failed.'.format(veda_id=veda_id))


class Command(BaseCommand):
    """
    Re-encode video from hotstore command class
    """
    help = 'Re-encode videos for HLS profile'

    def add_arguments(self, parser):
        super(Command, self).add_arguments(parser)

        # Optional arguments.
        parser.add_argument(
            '-vi',
            '--veda_id',
            help="VEDA video ID"
        )

    def handle(self, *args, **options):
        """
        handle method for command class.
        """
        settings = get_config()
        hls_profile = Encode.objects.get(product_spec='hls')

        LOGGER.info('[Re-encode for HLS] Process started.')

        veda_id = options.get('veda_id')
        if veda_id:
            try:
                video = Video.objects.filter(edx_id=veda_id).latest()
                enqueue_video_for_hls_encode(
                    veda_id=video.edx_id,
                    encode_queue=settings['celery_worker_queue']
                )
            except Video.DoesNotExist:
                LOGGER.warning('HLS encode is present for video=%s in VEDA.', veda_id)
        else:
            config = EncodeVideosMissingHlsConfiguration.current()
            all_videos = config.all_videos
            courses = config.course_ids.split(',')
            commit = config.commit

            edx_video_ids = []
            if all_videos:
                edx_video_ids = get_videos_wo_hls(batch_size=config.batch_size, offset=config.offset)
            elif courses:
                edx_video_ids = get_videos_wo_hls(courses=courses)

            veda_videos = Video.objects.filter(studio_id__in=edx_video_ids)
            veda_video_ids = veda_videos.values_list('edx_id', flat=True)
            videos_with_hls_encodes = (URL.objects
                                       .filter(encode_profile=hls_profile, videoID__veda_id__in=veda_video_ids)
                                       .values_list('videoID__edx_id')
                                       .distinct())

            # Log some stats about VEDA vs VAL videos.
            num_videos_found_in_veda = veda_videos.count()
            num_videos_not_found_in_veda = edx_video_ids - veda_videos.count()
            num_videos_hls_profile_found_in_veda = videos_with_hls_encodes.count()
            num_videos_actually_needing_hls_encode = veda_videos.count() - num_videos_hls_profile_found_in_veda
            LOGGER.info(
                (u"[run=%s] videos(found in VEDA)=%s - "
                 u"videos(not found in veda)=%s - "
                 u"videos(hls profile present)=%s - "
                 u"videos(hls profile not present)=%s."),
                config.command_run,
                num_videos_found_in_veda,
                num_videos_not_found_in_veda,
                num_videos_hls_profile_found_in_veda,
                num_videos_actually_needing_hls_encode,
            )

            # Check if this job is configured for dry run.
            if commit:
                for veda_id in veda_video_ids:
                    if veda_id not in videos_with_hls_encodes:
                        enqueue_video_for_hls_encode(
                            veda_id=veda_id,
                            encode_queue=settings['celery_worker_queue']
                        )
                    else:
                        LOGGER.warning(
                            '[run=%s] HLS encode is present for video=%s in VEDA.',
                            config.command_run,
                            veda_id
                        )
                        # TODO: update the URL's value in edxval directly

                config.increment_run()
                config.update_offset()
