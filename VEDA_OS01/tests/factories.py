"""
VEDA model factories.
"""
from __future__ import absolute_import
from factory import Sequence, SubFactory
from factory.django import DjangoModelFactory

from VEDA_OS01.models import Course, Destination, Encode, TranscriptStatus, URL, Video, VideoStatus


class CourseFactory(DjangoModelFactory):
    """
    Course data model factory.
    """
    class Meta(object):
        model = Course

    course_name = Sequence('Test Course {0}'.format)
    institution = Sequence('INST-{0}'.format)
    edx_classid = Sequence('CLASS-{0}'.format)
    semesterid = Sequence('2018-{0}'.format)
    proc_loc = False
    review_proc = False
    yt_proc = False
    s3_proc = False
    local_storedir = None


class VideoFactory(DjangoModelFactory):
    """
    Video data model factory.
    """
    class Meta(object):
        model = Video

    inst_class = SubFactory(CourseFactory)
    client_title = Sequence('Video {0}'.format)
    edx_id = Sequence('ABC-CDE-EFG-{0}'.format)
    studio_id = Sequence('61bd0526{0}'.format)
    video_trans_status = VideoStatus.SI
    transcript_status = TranscriptStatus.NOT_APPLICABLE
    process_transcription = False
    provider = None
    three_play_turnaround = None
    cielo24_turnaround = None
    cielo24_fidelity = None
    source_language = None
    preferred_languages = []


class DestinationFactory(DjangoModelFactory):
    """
    Destination data model factory.
    """
    class Meta(object):
        model = Destination

    destination_name = Sequence('Dest-{0}'.format)
    destination_active = False
    destination_nick = Sequence('D{0}'.format)


class EncodeFactory(DjangoModelFactory):
    """
    Encode data model factory.
    """
    class Meta(object):
        model = Encode

    encode_destination = SubFactory(DestinationFactory)
    encode_name = Sequence('Encode-{0}'.format)
    profile_active = False
    encode_suffix = ''
    encode_filetype = 'mp4'
    encode_bitdepth = None
    encode_resolution = None
    product_spec = None


class UrlFactory(DjangoModelFactory):
    """
    URL data model factory.
    """
    class Meta(object):
        model = URL

    encode_profile = SubFactory(EncodeFactory)
    videoID = SubFactory(VideoFactory)
    encode_url = Sequence('https://www.querty.com/{0}'.format)
