"""
Start Celery Worker
"""



from celery import Celery
import logging
import os
import sys

from VEDA.utils import get_config
try:
    from control.veda_deliver import VedaDelivery
except ImportError:
    from veda_deliver import VedaDelivery

from control.veda_heal import VedaHeal
from VEDA_OS01.models import Video

LOGGER = logging.getLogger(__name__)
# TODO: Remove this temporary logging to stdout
logging.basicConfig(stream=sys.stdout, level=logging.INFO)

auth_dict = get_config()

CEL_BROKER = 'redis://:@{redis_broker}:6379/0'.format(redis_broker=auth_dict['redis_broker'])

app = Celery(auth_dict['celery_app_name'], broker=CEL_BROKER, backend=CEL_BROKER, include=['celeryapp'])

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


@app.task(name=auth_dict['celery_online_heal_queue'])
def web_healer(veda_id):
    LOGGER.debug('[WEB_HEALER] id : {id}'.format(id=veda_id))
    vh = VedaHeal(
        video_query=Video.objects.filter(
            edx_id=veda_id.strip()
            ),
        no_audio=False
        )
    vh.send_encodes()


if __name__ == '__main__':
    app.start()
