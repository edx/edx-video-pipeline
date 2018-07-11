"""
Start Celery Worker
"""

from __future__ import absolute_import

from celery import Celery
import logging
import os
import sys

from VEDA.utils import get_config
try:
    from control.veda_deliver import VedaDelivery
except ImportError:
    from veda_deliver import VedaDelivery

LOGGER = logging.getLogger(__name__)
# TODO: Remove this temporary logging to stdout
logging.basicConfig(stream=sys.stdout, level=logging.INFO)

auth_dict = get_config()

CEL_BROKER = 'redis://:{redis_pass}@{redis_broker}:6379/0'.format(
    redis_pass=auth_dict['redis_pass'],
    redis_broker=auth_dict['redis_broker']
)

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


@app.task(name='worker_encode')
def worker_task_fire(veda_id, encode_profile, jobid):
    LOGGER.info('[ENCODE] Misfire : {id} : {encode}'.format(id=veda_id, encode=encode_profile))
    return 1


@app.task(name='supervisor_deliver')
def deliverable_route(veda_id, encode_profile):
    """
    Task for deliverable route.
    """
    veda_deliver = VedaDelivery(
        veda_id=veda_id,
        encode_profile=encode_profile
    )
    veda_deliver.run()


@app.task
def node_test(command):
    os.system(command)


@app.task(name='legacy_heal')
def maintainer_healer(command):
    os.system(command)


if __name__ == '__main__':
    app.start()
