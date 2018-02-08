"""
Production environment settings.
"""
from VEDA.settings.base import *
from VEDA.utils import get_config
from VEDA.settings.utils import get_logger_config

DEBUG = False
TEMPLATE_DEBUG = DEBUG
DEFATULT_SERVICE_VARIANT_NAME = 'video-pipeline'

ALLOWED_HOSTS = ['*']

CONFIG_DATA = get_config()

LOGGING = get_logger_config(service_variant=CONFIG_DATA.get('SERVICE_VARIANT_NAME', DEFATULT_SERVICE_VARIANT_NAME))

# Keep track of the names of settings that represent dicts. Instead of overriding the values in base.py,
# the values read from disk should UPDATE the pre-configured dicts.
DICT_UPDATE_KEYS = ('DATABASES',)

# Remove the items that should be used to update dicts, and apply them separately rather
# than pumping them into the local vars.
dict_updates = {key: CONFIG_DATA.pop(key, None) for key in DICT_UPDATE_KEYS}

for key, value in dict_updates.items():
    if value:
        vars()[key].update(value)

vars().update(CONFIG_DATA)

JWT_AUTH = {
    'JWT_SECRET_KEY': CONFIG_DATA['val_secret_key'],
    'JWT_ISSUER': '{}/oauth2'.format(CONFIG_DATA['lms_base_url'].rstrip('/')),
    'JWT_AUDIENCE': CONFIG_DATA['val_client_id'],
    'JWT_VERIFY_AUDIENCE': True,
}
