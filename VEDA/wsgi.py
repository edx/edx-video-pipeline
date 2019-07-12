"""
"""
from __future__ import absolute_import
import os
from django.core.wsgi import get_wsgi_application

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("PYTHON_EGG_CACHE", BASE_DIR + "/egg_cache")
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'VEDA.settings.local')
application = get_wsgi_application()
