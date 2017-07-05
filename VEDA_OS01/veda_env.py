#!/usr/bin/env python

import os
import sys
import django

"""
VEDA Environment variables

"""

"""
Import Django Shit
"""
project_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_path not in sys.path:
    sys.path.append(project_path)

os.environ['DJANGO_SETTINGS_MODULE'] = 'VEDA.settings'

django.setup()

from VEDA_OS01.models import Institution
from VEDA_OS01.models import Course
from VEDA_OS01.models import Video
from VEDA_OS01.models import URL
from VEDA_OS01.models import VedaUpload
