"""
Destroy Out of date tokens
"""
import os
import sys
import datetime
from datetime import timedelta

project_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_path not in sys.path:
    sys.path.append(project_path)

from control.control_env import *

from oauth2_provider.models import AccessToken


def get_tokens():
    auth_query = AccessToken.objects.filter(
        expires__lt=datetime.datetime.now() - timedelta(hours=1),
    )
    for a in auth_query:
        AccessToken.objects.filter(token=a.token).delete()
        print a.token
    print len(auth_query)


if __name__ == '__main__':
    get_tokens()
