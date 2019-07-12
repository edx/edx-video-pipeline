"""
Test settings

"""
from __future__ import absolute_import
from VEDA.settings.base import *
from VEDA.settings.utils import get_logger_config

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': 'pipeline.db',
    }
}

FERNET_KEYS = ['test-ferent-key']

LOGGING = get_logger_config(debug=False, dev_env=True, local_loglevel='DEBUG')
