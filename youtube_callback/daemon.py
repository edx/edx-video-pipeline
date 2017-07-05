"""
Youtube Primary Reporting / Callbacks
"""

import os
import sys
import datetime
from datetime import timedelta
import django
import newrelic.agent

from django.utils.timezone import utc

from VEDA_OS01.models import Course, Video, Encode, URL

"""
Import Django Shit
"""
project_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_path not in sys.path:
    sys.path.append(project_path)

os.environ['DJANGO_SETTINGS_MODULE'] = 'VEDA.settings'

django.setup()

newrelic.agent.initialize(
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'veda_newrelic.ini'
    )
)

"""
Defaults
"""
data_window = datetime.datetime.utcnow().replace(tzinfo=utc) - \
    timedelta(days=15)


def get_course(course_id):
    course = Course.objects.get(
        institution=course_id[0:3],
        edx_classid=course_id[3:8]
    )
    return course


@newrelic.agent.background_task()
def generate_course_list():

    course_list = []

    course_query = Course.objects.filter(
        previous_statechange__gt=data_window,
        yt_proc=True,
    )

    for course in course_query:
        if determine_missing_url(course_object=course) is True:
            if weed_dupes(course_list, course) is True:
                course_list.append(course)
    """
    Review Calls
    """
    review_date = datetime.datetime.utcnow().replace(tzinfo=utc) - \
        timedelta(days=10)
    review_query = Course.objects.filter(
        previous_statechange__gt=review_date,
        review_proc=True
    )
    if len(review_query) > 0:
        review_channel = Course.objects.get(
            institution='EDX',
            edx_classid='RVW01'
        )
        course_list.append(review_channel)

    return course_list


@newrelic.agent.background_task()
def weed_dupes(course_list, course):
    for c in course_list:
        if c.yt_logon == course.yt_logon:
            return False
    return True


@newrelic.agent.background_task()
def determine_missing_url(course_object):

    video_query = Video.objects.filter(
        inst_class=course_object,
        video_trans_start__gt=data_window
    )
    for v in video_query:
        salient_video = Video.objects.filter(edx_id=v.edx_id).latest()
        if salient_video.video_trans_status != "Corrupt File" and \
                salient_video.video_trans_status != "Review Hold":
            yt_url_query = URL.objects.filter(
                videoID=salient_video,
                encode_profile=Encode.objects.filter(
                    encode_suffix='100'
                )
            )
            if len(yt_url_query) == 0:
                return True
    return False


if __name__ == "__main__":
    pass
