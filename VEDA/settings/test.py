"""
Test settings

"""
from VEDA.settings.base import *

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': 'pipeline.db',
    }
}
