"""
Start Celery Worker
"""

from __future__ import absolute_import

from celery import Celery
import logging
import sys
import boto
from boto.exception import S3ResponseError

from VEDA.utils import get_config
from control.veda_file_discovery import FileDiscovery


LOGGER = logging.getLogger(__name__)
# TODO: Remove this temporary logging to stdout
logging.basicConfig(stream=sys.stdout, level=logging.INFO)

auth_dict = get_config()

CEL_BROKER = 'redis://:@{redis_broker}:6379/0'.format(redis_broker=auth_dict['redis_broker'])

app = Celery(auth_dict['celery_app_name'], broker=CEL_BROKER, include=['http_ingest_celeryapp'])

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


@app.task(name=auth_dict['celery_http_ingest_queue'])
def ingest_video_and_upload_to_hotstore(requested_key):
    LOGGER.info('ingest_video_and_upload_to_hotstore key %s' % requested_key)
    bucket_name = auth_dict['edx_s3_ingest_bucket']
    try:
        connection = boto.connect_s3()
        bucket = connection.get_bucket(bucket_name)
        s3_key = bucket.get_key(requested_key)
    except S3ResponseError:
        LOGGER.error('[INGEST CELERY TASK] Could not connect to S3, key %s' % requested_key)
        return

    file_discovery = FileDiscovery()
    file_discovery.bucket = bucket
    successful_ingest = file_discovery.validate_metadata_and_feed_to_ingest(video_s3_key=s3_key)
    if not successful_ingest:
        LOGGER.error('[INGEST CELERY TASK] Ingest failed for key %s' % requested_key)
    return


if __name__ == '__main__':
    app.start()
