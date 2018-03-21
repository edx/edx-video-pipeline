import os
import sys

from celery.task.control import revoke

project_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_path not in sys.path:
    sys.path.append(project_path)

import control.celeryapp

tasks_to_cancel = [
'1386bfc2-ccb5-46e4-8971-33e7092f3cd2',
'980b763a-6531-4a25-970c-5b3b5cbf6361'
]

for t in tasks_to_cancel:
    revoke(t, terminate=True)
