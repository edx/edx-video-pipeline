"""
Common utils.
"""
import os
import yaml
import urllib

from opaque_keys import InvalidKeyError
from opaque_keys.edx.keys import CourseKey

DEFAULT_CONFIG_FILE_PATH = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_CONFIG_FILE_NAME = 'instance_config.yaml'


def extract_course_org(course_id):
    """
    Extract video organization from course url.
    """
    org = None

    try:
        org = CourseKey.from_string(course_id).org
    except InvalidKeyError:
        pass

    return org


def build_url(*urls, **query_params):
    """
    Build a url from specified params.

    Arguments:
        base_url (str): base url
        relative_url (str): endpoint
        query_params (dict): query params

    Returns:
        absolute url
    """
    url = '/'.join(item.strip('/') for item in urls)
    if query_params:
        url = '{}?{}'.format(url, urllib.urlencode(query_params))

    return url


def get_config(yaml_config_file=DEFAULT_CONFIG_FILE_NAME):
    """
    Read yaml config file.

    Arguments:
        yaml_config_file (str): yaml config file name

    Returns:
        dict: yaml config
    """
    config_dict = {}

    try:
        yaml_config_file = os.environ['VIDEO_PIPELINE_CFG']
    except KeyError:
        yaml_config_file = os.path.join(
            DEFAULT_CONFIG_FILE_PATH,
            yaml_config_file
        )

    with open(yaml_config_file, 'r') as config:
        config_dict = yaml.load(config)

    return config_dict
