from VEDA.settings.base import *

DEBUG = True
ALLOWED_HOSTS = ['*']

# DATABASE CONFIGURATION
# See: https://docs.djangoproject.com/en/dev/ref/settings/#databases
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': os.path.join(ROOT_DIR, 'sandbox.db'),
        'USER': '',
        'PASSWORD': '',
        'HOST': '',
        'PORT': '',
    }
}
# END DATABASE CONFIGURATION

JWT_AUTH.update({
    'JWT_SECRET_KEY': 'lms-secret',
    'JWT_ISSUER': 'http://127.0.0.1:8000/oauth2',
    'JWT_AUDIENCE': 'lms-key',
    'JWT_VERIFY_AUDIENCE': False
})

# See if the developer has any local overrides.
if os.path.isfile(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'private.py')):
    from .private import *  # pylint: disable=import-error, wildcard-import
