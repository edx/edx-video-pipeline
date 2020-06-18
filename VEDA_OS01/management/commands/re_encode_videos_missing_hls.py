"""
Management command used to re-encode video for HLS profiles.

 - Request edxval for set of videos to re-encode
 - Retrieve corresponding VEDA Video object and switch off process_transcription flag. This is required
   to avoid unintentional transcription that happens in Delivery phase.
 - Check VEDA to see whether an HLS profile is there and if it does then, just update edxval with it otherwise
   kick off encoding task (a.k.a worker_tasks_fire) with veda_id and encode_profile=HLS.
 - Encode worker generates the HLS encode, push it S3 and initiate a delivery task
 - Deliver worker process the delivery task and delivers the successful HLS encode profile to edxval

"""

import ast
import logging
import uuid

import boto

from django.core.management.base import BaseCommand, CommandError
from django.db.models.query_utils import Q
from opaque_keys import InvalidKeyError
from opaque_keys.edx.keys import CourseKey
from requests import post, put
from six import text_type

from VEDA_OS01.models import Video, EncodeVideosForHlsConfiguration, URL, Encode
from VEDA.utils import get_config
from control.encode_worker_tasks import enqueue_encode

LOGGER = logging.getLogger(__name__)
BUCKET_NAME = 'veda-hotstore'


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
    response = post(settings['val_token_url'], data=payload, timeout=settings['global_timeout'])

    if response.status_code == 200:
        token = ast.literal_eval(response.text)['access_token']
    else:
        LOGGER.error('EDXVAL Token Generation Error: %s', response.text)

    return token


def get_api_url_and_auth_headers():
    """
    Construct request headers.
    """
    settings = get_config()
    token = get_auth_token(settings)
    if not token:
        return settings['val_api_url'], token

    # Build and return request headers.
    headers = {
        'Authorization': 'Bearer {token}'.format(token=token),
        'content-type': 'application/json'
    }
    return settings['val_api_url'], headers


def get_videos_wo_hls(courses=None, batch_size=None, offset=None):
    """
    Get videos from edxval which are missing HLS profiles.

    Arguments:
        courses: List of course IDs
        batch_size: Number of videos per batch
        offset: Position to pick the batch of videos
    """
    api_url, headers = get_api_url_and_auth_headers()
    if not headers:
        return

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
    val_videos_url = '/'.join([api_url, 'missing-hls/'])
    response = post(val_videos_url, json=params, headers=headers)

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


def update_hls_profile_in_val(api_url, headers, edx_video_id, profile, encode_data):
    """
    Update HLS profile in VAL for a video.
    """
    payload = {
        'edx_video_id': edx_video_id,
        'profile': profile,
        'encode_data': encode_data
    }
    val_profile_update_url = '/'.join([api_url, 'missing-hls/'])
    response = put(val_profile_update_url, json=payload, headers=headers)
    return response


def enqueue_video_for_hls_encode(veda_id, encode_queue):
    """
    Enqueue HLS encoding task.
    """
    task_id = uuid.uuid1().hex[0:10]
    enqueue_encode(veda_id, 'hls', task_id, encode_queue, update_val_status=False)


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

    def _validate_course_ids(self, course_ids):
        """
        Validate a list of course key strings.
        """
        try:
            for course_id in course_ids:
                CourseKey.from_string(course_id)
            return course_ids
        except InvalidKeyError as error:
            raise CommandError('Invalid key specified: {}'.format(text_type(error)))

    def _validate_video_encode(self, video_encode):
        """
        Validate video encode object for
        number of attributes.
        """
        is_valid = True
        required_attrs = ('encode_size', 'encode_bitdepth', 'encode_url')
        for attr in required_attrs:
            if getattr(video_encode, attr) is None:
                is_valid = False
                LOGGER.info('Validation Error: video=%s - missing=%s', video_encode.videoID.edx_id, attr)
                break

        return is_valid

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
                    encode_queue=settings['celery_worker_low_queue']
                )
            except Video.DoesNotExist:
                LOGGER.warning('Video "%s" not found.', veda_id)
        else:
            config = EncodeVideosForHlsConfiguration.current()
            all_videos = config.all_videos
            courses = self._validate_course_ids(course_ids=config.course_ids.split())
            commit = config.commit

            if all_videos:
                edx_video_ids = get_videos_wo_hls(batch_size=config.batch_size, offset=config.offset)
            elif courses:
                edx_video_ids = get_videos_wo_hls(courses=courses)
            else:
                LOGGER.info('Missing job configuration.')
                return

            # Result will be None if we are Unable
            # to retrieve edxval Token.
            if edx_video_ids is None:
                LOGGER.error('Unable to get edxval Token.')
                return

            veda_videos = Video.objects.filter(Q(studio_id__in=edx_video_ids) | Q(edx_id__in=edx_video_ids))
            veda_video_ids = veda_videos.values_list('edx_id', flat=True)
            videos_with_hls_encodes = (URL.objects
                                       .filter(encode_profile=hls_profile, videoID__edx_id__in=veda_video_ids)
                                       .values_list('videoID__edx_id', flat=True)
                                       .distinct())

            # Log stats about VEDA vs VAL videos.
            num_videos_found_in_veda = veda_videos.count()
            num_videos_not_found_in_veda = len(edx_video_ids) - veda_videos.count()
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
                api_url, headers = get_api_url_and_auth_headers()
                if not headers:
                    LOGGER.error('No headers. Unable to get VAL token.')
                    return

                for veda_id in veda_video_ids:
                    LOGGER.info('Processing veda_id %s', veda_id)
                    video = veda_videos.filter(edx_id=veda_id).latest()
                    if veda_id in videos_with_hls_encodes:
                        # Update the URL's value in edxval directly
                        LOGGER.warning(
                            '[run=%s] HLS encode is present for video=%s in VEDA.',
                            config.command_run,
                            veda_id
                        )
                        try:
                            video_encode = URL.objects.filter(
                                videoID=video,
                                encode_profile=hls_profile
                            ).latest()
                        except URL.DoesNotExist:
                            LOGGER.warning(
                                '[run=%s] HLS encode not found for video=%s in VEDA.',
                                config.command_run,
                                veda_id
                            )
                            continue

                        if self._validate_video_encode(video_encode):
                            edx_video_id = video.studio_id or video.edx_id
                            response = update_hls_profile_in_val(api_url, headers, edx_video_id, 'hls', encode_data={
                                'file_size': video_encode.encode_size,
                                'bitrate': int(video_encode.encode_bitdepth.split(' ')[0]),
                                'url': video_encode.encode_url
                            })

                            # Response will be None if we are Unable to get edxval Token.
                            if response is None:
                                LOGGER.info('Unable to get edxval Token.')
                                continue

                            if response.status_code == 200:
                                LOGGER.info("[run=%s] Success for video=%s.", config.command_run, veda_id)
                            else:
                                LOGGER.warning(
                                    "[run=%s] Failure on VAL update - status_code=%s, video=%s, traceback=%s.",
                                    config.command_run,
                                    response.status_code,
                                    veda_id,
                                    response.text
                                )
                            continue
                        else:
                            # After this clause, veda_id will be re-enqueued for HLS encoding since the
                            # encode data is corrupt.
                            LOGGER.warning(
                                '[run=%s] HLS encode data was corrupt for video=%s in VEDA - Re-enqueueing..',
                                config.command_run,
                                veda_id
                            )

                    # Disable transcription

                    video.process_transcription = False
                    video.save()

                    # Enqueue video for HLS re-encode.
                    LOGGER.info('Enqueueing id %s for hls encode', veda_id)
                    enqueue_video_for_hls_encode(
                        veda_id=veda_id,
                        encode_queue=settings['celery_worker_low_queue']
                    )

                config.increment_run()
                config.update_offset()
            else:
                videos_not_in_hotstore = 0
                for veda_id in veda_video_ids:
                    if source_video_not_in_hotstore(veda_id):
                        videos_not_in_hotstore += 1
                        LOGGER.info('VEDA ID %s not found in hotstore', veda_id)
                LOGGER.info('Number of videos missing source: %d', videos_not_in_hotstore)
                LOGGER.info('[run=%s] Dry run is complete.', config.command_run)


def source_video_not_in_hotstore(video_id):
    try:
        video = Video.objects.filter(edx_id=video_id).latest()
    except Exception as e:
        LOGGER.error('Exception during VEDA lookup: %s', e)
        return True
    if not video:
        LOGGER.error('Video ID %s not found in VEDA', video_id)
        return True

    conn = boto.connect_s3()
    bucket = conn.get_bucket(BUCKET_NAME)

    if not video.video_orig_extension:
        LOGGER.info('Cannot look up %s, unknown extension', video_id)
        return True
    key_name = video.edx_id + '.' + video.video_orig_extension
    try:
        if not bucket.get_key(key_name):
            return True
        else:
            return False
    except Exception as e:
        LOGGER.error('Exception during get_key: %s', e)
        return True
