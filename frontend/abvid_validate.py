'''
About Video Input and Validation
'''

import os
import sys
import datetime


from veda_env import *


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

    ul2 = VedaUpload.objects.filter(
        video_serial=upload_data['abvid_serial']
    ).update(
        upload_date=datetime.datetime.utcnow().replace(tzinfo=utc),
        upload_filename=upload_data['orig_filename'],
    )
    return True


def send_to_pipeline(upload_data):

    ul3 = VedaUpload.objects.filter(
        video_serial=upload_data['abvid_serial']
    ).update(
        file_valid=upload_data['success'],
    )

    if upload_data['success'] == 'true':
        print 'Sending File to Pipeline'

    else:
        ul3 = VedaUpload.objects.filter(
            video_serial=upload_data['abvid_serial']
        ).update(
            comment='Failed Upload',
        )
        return False

if __name__ == '__main__':
    upload_data = {}
    upload_data['abvid_serial'] = '19e1e1c78e'
    upload_data['success'] = 'true'
    send_to_pipeline(upload_data)
