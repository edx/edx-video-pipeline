"""
Production environment settings.
"""
from VEDA.settings.base import *
from VEDA.utils import get_config
from VEDA.settings.utils import get_logger_config

DEBUG = False
TEMPLATE_DEBUG = DEBUG

ALLOWED_HOSTS = ['*']

LOGGING = get_logger_config(debug=True)

# Keep track of the names of settings that represent dicts. Instead of overriding the values in base.py,
# the values read from disk should UPDATE the pre-configured dicts.
DICT_UPDATE_KEYS = ('DATABASES', 'JWT_AUTH')

CONFIG_DATA = get_config()
# Remove the items that should be used to update dicts, and apply them separately rather
# than pumping them into the local vars.
dict_updates = {key: CONFIG_DATA.pop(key, None) for key in DICT_UPDATE_KEYS}

for key, value in dict_updates.items():
    if value:
        vars()[key].update(value)

vars().update(CONFIG_DATA)
