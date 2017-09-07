"""
Common utils.
"""
import os
import urllib

import yaml
from opaque_keys import InvalidKeyError
from opaque_keys.edx.keys import CourseKey


def get_config(yaml_config_file='instance_config.yaml'):
    """
    Read yaml config file.

    Arguments:
        yaml_config_file (str): yaml config file name

    Returns:
        dict: yaml conifg
    """
    config_dict = {}

    yaml_config_file = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        yaml_config_file
    )

    with open(yaml_config_file, 'r') as config:
        try:
            config_dict = yaml.load(config)
        except yaml.YAMLError:
            pass

    return config_dict


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


def update_video_status(val_api_client, video, status):
    """
    Updates video status both in edx-val and edx-video-pipeline.

    Arguments:
        video(Video): Video data model object
        status(Str): Video status to be updated
    """
    # update edx-val's video status
    val_api_client.update_video_status(
        video.studio_id, status
    )

    # update edx-video-pipeline's video status
    video.video_trans_status = status
    video.save()
