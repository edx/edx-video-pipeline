"""
About Video Input and Validation

"""

from __future__ import absolute_import
import datetime
import logging

from frontend.frontend_env import *

LOGGER = logging.getLogger(__name__)
# TODO: Remove this temporary logging to stdout
logging.basicConfig(stream=sys.stdout, level=logging.INFO)


def create_record(upload_data):
    """
    Create Record
    """
    ul1 = VedaUpload(
        video_serial=upload_data['abvid_serial'],
        edx_studio_url=upload_data['studio_url'],
        client_information=upload_data['course_name'],
        status_email=upload_data['pm_email'],
        file_valid=False,
        file_complete=False,
    )
    try:
        ul1.save()
        return True
    except:
        return False


def validate_incoming(upload_data):

    VedaUpload.objects.filter(
        video_serial=upload_data['abvid_serial']
    ).update(
        upload_date=datetime.datetime.utcnow().replace(tzinfo=utc),
        upload_filename=upload_data['orig_filename'],
    )
    return True


def send_to_pipeline(upload_data):
    VedaUpload.objects.filter(
        video_serial=upload_data['abvid_serial']
    ).update(
        file_valid=upload_data['success'],
    )
    if upload_data['success'] == 'True':
        LOGGER.info('[ABOUT_VIDEO] {ul_id} : Sending File to Pipeline'.format(
            ul_id=upload_data['abvid_serial']
        ))
        return True

    # Failed upload
    VedaUpload.objects.filter(
        video_serial=upload_data['abvid_serial']
    ).update(
        comment='Failed Upload',
    )
    LOGGER.info('[ABOUT_VIDEO] {ul_id} : Failed upload'.format(
        ul_id=upload_data['abvid_serial']
    ))
    return False
