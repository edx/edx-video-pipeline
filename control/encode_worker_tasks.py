"""
This module contains calls to remote celery tasks that are run by the veda encode worker.
The code for those tasks lives in the edx-video-worker repository.
"""


from celery import Celery
from VEDA.utils import get_config

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


def enqueue_encode(veda_id, encode_profile, job_id, encode_worker_queue, update_val_status=True):
    """
    Send an encode request to the remote encode worker.
    """
    app.send_task('worker_encode', args=(veda_id, encode_profile, job_id, update_val_status),
                  queue=encode_worker_queue, connect_timeout=3)
