"""
Stage environment settings.
"""
from __future__ import absolute_import
from VEDA.settings.base import *
from VEDA.utils import get_config
from VEDA.settings.utils import get_logger_config

DEBUG = False
TEMPLATE_DEBUG = DEBUG
DEFATULT_SERVICE_VARIANT_NAME = 'video-pipeline'

ALLOWED_HOSTS = ['*']

CONFIG_DATA = get_config()

LOGGING = get_logger_config(service_variant=CONFIG_DATA.get('SERVICE_VARIANT_NAME', DEFATULT_SERVICE_VARIANT_NAME))

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': os.path.join(ROOT_DIR, 'stage.db'),
        'USER': '',
        'PASSWORD': '',
        'HOST': '',
        'PORT': '',
    }
}
