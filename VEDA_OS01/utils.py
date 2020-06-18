"""
Common utils.
"""

from rest_framework.parsers import BaseParser

from VEDA.utils import get_config
from VEDA_OS01.models import Encode, TranscriptStatus, URL, Video
import six


class ValTranscriptStatus(object):
    """
    VAL supported video transcript statuses.
    """
    TRANSCRIPTION_IN_PROGRESS = 'transcription_in_progress'
    TRANSCRIPT_READY = 'transcript_ready'


# Maps the edx-video-pipeline video transcript statuses to edx-val statuses.
VAL_TRANSCRIPT_STATUS_MAP = {
    TranscriptStatus.IN_PROGRESS: ValTranscriptStatus.TRANSCRIPTION_IN_PROGRESS,
    TranscriptStatus.READY: ValTranscriptStatus.TRANSCRIPT_READY
}


def update_video_status(val_api_client, video, status):
    """
    Updates video status both in edx-val and edx-video-pipeline.

    Arguments:
        video(Video): Video data model object
        status(Str): Video status to be updated
    """
    # update edx-val's video status
    try:
        val_status = VAL_TRANSCRIPT_STATUS_MAP[status]
        val_api_client.update_video_status(video.studio_id, val_status)
    except KeyError:
        # Don't update edx-val's video status.
        pass

    # update edx-video-pipeline's video status
    video.transcript_status = status
    video.save()


def invalidate_fernet_cached_properties(model, fields):
    """
    Invalidates transcript credential fernet field's cached properties.

    Arguments:
        model (class): Model class containing fernet fields.
        fields (list):  A list of fernet fields whose cache is to be invalidated.
    """
    for field_name in fields:
        try:
            field = model._meta.get_field(field_name)
            del field.keys
            del field.fernet_keys
            del field.fernet
        except AttributeError:
            pass


def get_incomplete_encodes(edx_id):
    """
    Get incomplete encodes for the given video.

    Arguments:
        edx_id(unicode): an ID identifying the VEDA video.
    """
    encode_list = []
    try:
        video = Video.objects.filter(edx_id=edx_id).latest()
    except Video.DoesNotExist:
        return encode_list

    course = video.inst_class
    # Pick the encodes map from the settings.
    encodes_map = get_config().get('encode_dict', {})
    # Active encodes according to course instance.
    for attr, encodes in six.iteritems(encodes_map):
        if getattr(course, attr, False):
            encode_list += [encode.strip() for encode in encodes]

    # Filter active encodes further according to their corresponding encode profiles activation.
    for encode in list(encode_list):
        encode_profile = Encode.objects.filter(product_spec=encode).first()
        if not encode_profile or (encode_profile and not encode_profile.profile_active):
            encode_list.remove(encode)

    # Filter encodes based on their successful encoding for the specified video.
    for encode in list(encode_list):
        completed_encode_profile = URL.objects.filter(
            videoID=video,
            encode_profile__product_spec=encode
        )
        if completed_encode_profile.exists():
            encode_list.remove(encode)

    return encode_list


def is_video_ready(edx_id, ignore_encodes=list()):
    """
    Check whether a video should be considered ready.

    Arguments:
        edx_id(unicode): An ID identifying the VEDA video.
        ignore_encodes(list): A list containing the profiles that should not be considered.
    """
    return set(get_incomplete_encodes(edx_id)).issubset(set(ignore_encodes))


class PlainTextParser(BaseParser):
    """
    Plain text parser.
    """
    media_type = 'text/plain'

    def parse(self, stream, media_type=None, parser_context=None):
        """
        Simply return a string representing the body of the request.
        """
        return stream.read()
