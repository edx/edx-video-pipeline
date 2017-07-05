"""
VEDA's Django Secrets
NEVER SHARE ANYTHING IN HERE, like, EVER
--assume unchanged in git--
"""

import os

DJANGO_SECRET_KEY = ""

DJANGO_DB_USER = ""
DJANGO_DB_PASS = ""

DJANGO_ADMIN = ('', '')

SANDBOX_TOKEN = None

if SANDBOX_TOKEN is not None and SANDBOX_TOKEN in os.path.dirname(__file__):
    DEBUG = True
    DBHOST = ''
    veda_dbname = ""
else:
    DEBUG = False
    DBHOST = ''
    veda_dbname = ""
