
from __future__ import absolute_import
import os
import sys
from celery import Celery
import yaml

"""
Start Celery Worker

"""
try:
    from control.control_env import *
except:
    from control_env import *

try:
    from control.veda_deliver import VedaDelivery
except:
    from veda_deliver import VedaDelivery

auth_yaml = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'instance_config.yaml'
)
with open(auth_yaml, 'r') as stream:
    try:
        auth_dict = yaml.load(stream)
    except yaml.YAMLError as exc:
        auth_dict = None

CEL_BROKER = 'amqp://{rabbitmq_user}:{rabbitmq_pass}@{rabbitmq_broker}:5672//'.format(
    rabbitmq_user=auth_dict['rabbitmq_user'],
    rabbitmq_pass=auth_dict['rabbitmq_pass'],
    rabbitmq_broker=auth_dict['rabbitmq_broker']
)

CEL_BACKEND = 'amqp://{rabbitmq_user}:{rabbitmq_pass}@{rabbitmq_broker}:5672//'.format(
    rabbitmq_user=auth_dict['rabbitmq_user'],
    rabbitmq_pass=auth_dict['rabbitmq_pass'],
    rabbitmq_broker=auth_dict['rabbitmq_broker']
)

app = Celery(auth_dict['celery_app_name'], broker=CEL_BROKER, backend=CEL_BACKEND, include=[])

app.conf.update(
    BROKER_CONNECTION_TIMEOUT=60,
    CELERY_IGNORE_RESULT=True,
    CELERY_TASK_RESULT_EXPIRES=10,
    CELERYD_PREFETCH_MULTIPLIER=1,
    CELERY_ACCEPT_CONTENT=['pickle', 'json', 'msgpack', 'yaml']
)


@app.task(name='worker_encode')
def worker_task_fire(veda_id, encode_profile, jobid):
    pass


@app.task(name='supervisor_deliver')
def deliverable_route(veda_id, encode_profile):

    VD = VedaDelivery(
        veda_id=veda_id,
        encode_profile=encode_profile
    )
    VD.run()


@app.task
def node_test(command):
    os.system(command)


@app.task(name='legacy_heal')
def maintainer_healer(command):
    os.system(command)


if __name__ == '__main__':
    app.start()
