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

os.environ['DJANGO_SETTINGS_MODULE'] = 'common.settings'

django.setup()

from pipeline.models import Institution
from pipeline.models import Course
from pipeline.models import Video
from pipeline.models import URL
from pipeline.models import VedaUpload
