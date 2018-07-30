"""
Celery worker for ingest
"""

from __future__ import absolute_import

from celery import Celery
import logging
import sys

from control.control_env import WORK_DIRECTORY
from control.veda_file_ingest import VedaIngest, VideoProto
from control.veda_utils import get_video_metadata_from_studio_id
from VEDA.utils import get_config
from VEDA_OS01.models import Course

LOGGER = logging.getLogger(__name__)
# TODO: Remove this temporary logging to stdout
logging.basicConfig(stream=sys.stdout, level=logging.INFO)

auth_dict = get_config()

CEL_BROKER = 'redis://:@{redis_broker}:6379/0'.format(redis_broker=auth_dict['redis_broker'])

app = Celery(auth_dict['celery_app_name'], broker=CEL_BROKER, include=['celeryapp'])

app.conf.update(
    BROKER_CONNECTION_TIMEOUT=60,
    CELERY_IGNORE_RESULT=True,
    CELERY_TASK_RESULT_EXPIRES=10,
    CELERYD_PREFETCH_MULTIPLIER=1,
    CELERY_ACCEPT_CONTENT=['json'],
    CELERY_TASK_PUBLISH_RETRY=True,
    CELERY_TASK_PUBLISH_RETRY_POLICY={
        "max_retries": 3,
        "interval_start": 0,
        "interval_step": 1,
        "interval_max": 5
    }
)


@app.task(name='ingest_worker')
def ingest(s3_key_id, course_id, video_edx_id):
    """
    Ingest a video in s3.
    Arguments:
        - s3_key_id: a valid studio upload ID
        - course_id: course id identifying a course run
        - video_edx_id: the edX ID of the video in the database
    """
    course = Course.objects.get(id=course_id)
    video_metadata = get_video_metadata_from_studio_id(
        s3_key_id,
        video_edx_id
    )
    veda_ingest = VedaIngest(
        course_object=course,
        video_proto=VideoProto(**video_metadata),
        node_work_directory=WORK_DIRECTORY,
        s3_key_id=s3_key_id
    )
    veda_ingest.ingest_from_s3()


if __name__ == '__main__':
    app.start()
