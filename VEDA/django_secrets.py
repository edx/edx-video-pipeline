"""
Video Pipeline Django Secrets Shim

This acts as a django-secret shimmer until we can finish pushing all changes to terraform/prod

"""
import os
from VEDA.utils import get_config

CONFIG_DATA = get_config()


DJANGO_SECRET_KEY = CONFIG_DATA['django_secret_key'] or 'test_secret_key'
DJANGO_ADMIN = ('', '')
DJANGO_DEBUG = CONFIG_DATA['debug'] if 'debug' in CONFIG_DATA else False
DATABASES = CONFIG_DATA['DATABASES']
STATIC_ROOT_PATH = CONFIG_DATA.get(
    'STATIC_ROOT_PATH',
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'static'
    )
)
