"""
VEDA's Django Secrets Shim

This acts as a django-secret shimmer until we can finish pushing all changes to terraform/prod

"""
import os
import yaml

read_yaml = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'instance_config.yaml'
)

with open(read_yaml, 'r') as stream:
    try:
        return_dict = yaml.load(stream)
    except yaml.YAMLError as exc:
        return_dict = None


DJANGO_SECRET_KEY = return_dict['django_secret_key']
DJANGO_ADMIN = ('', '')
DEBUG = True
DATABASES = return_dict['DATABASES']
