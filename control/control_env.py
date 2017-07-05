#!/usr/bin/env python
"""
VEDA Environment variables

"""

import os
import sys
import django
from django.utils.timezone import utc
from django.db import reset_queries

project_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_path not in sys.path:
    sys.path.append(project_path)

os.environ['DJANGO_SETTINGS_MODULE'] = 'common.settings'

django.setup()

from pipeline.models import Institution
from pipeline.models import Course
from pipeline.models import Video
from pipeline.models import Destination
from pipeline.models import Encode
from pipeline.models import URL
from pipeline.models import VedaUpload

"""
Central Config
"""
WORK_DIRECTORY = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    'VEDA_WORKING'
)

if not os.path.exists(WORK_DIRECTORY):
    os.mkdir(WORK_DIRECTORY)

"""
Occasionally this throws an error in the env,
but on EC2 with v_videocompile it's no biggie

"""
FFPROBE = "ffprobe"
FFMPEG = "ffmpeg"

"""
Generalized display and such

"""

"""
TERM COLORS
"""
NODE_COLORS_BLUE = '\033[94m'
NODE_COLORS_GREEN = '\033[92m'
NODE_COLORS_RED = '\033[91m'
NODE_COLORS_END = '\033[0m'
