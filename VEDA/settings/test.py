"""
Test settings

"""
from VEDA.settings.base import *
from VEDA.settings.utils import get_logger_config

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': 'pipeline.db',
    }
}

LOGGING = get_logger_config(debug=False, dev_env=True, local_loglevel='DEBUG')
