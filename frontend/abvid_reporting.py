import os
import sys
from email.mime.text import MIMEText
from datetime import date
import boto.ses
from VEDA.utils import get_config

'''
ABVID REPORTING - email / etc.

'''
from frontend_env import *

'''
v1 = Video.objects.filter(edx_id = upload_info['edx_id'])
if v1.abvid_serial != None:
    sys.path.append(up_twodirectory + '/VEDA_OS/VEDA_FE/')
    import abvid_reporting
    abvid_reporting.report_status(
        status="Youtube Duplicate",
        abvid_serial = v1.abvid_serial,
        youtube_id = ''
        )
'''
"""
get auth keys from instance yaml

"""
auth_dict = get_config()


def report_status(status, abvid_serial, youtube_id):
    try:
        v1 = VedaUpload.objects.filter(video_serial=abvid_serial).latest()
    except ObjectDoesNotExist:
        return

    if len(youtube_id) > 0:
        excuse = ''

    if 'Duplicate' in status or 'Corrupt' in status:
        if v1.final_report is True:
            send_email = False
            # pass
        else:
            excuse = 'There has been a failure for the following reason : ' + status
            final_success = 'FAILED'
            youtube_id = ''
            VedaUpload.objects.filter(
                pk=v1.pk
            ).update(
                file_complete=False,
                final_report=True,
                file_valid=False
            )
            send_email = True
    elif 'Complete' in status:
        excuse = 'This file is complete.'
        final_success = 'SUCCESS'
        VedaUpload.objects.filter(
            pk=v1.pk
        ).update(
            file_complete=True,
            final_report=True,
            file_valid=True,
            youtube_id=youtube_id
        )
        send_email = True

    if send_email is True:
        email_subject = 'VEDA / edX About Video Status Update : ' + final_success

        email_body = 'This is an auto generated message:\n\n'
        email_body += 'An edX partner uploaded a new about video:\n\n'
        email_body += 'STATUS : ' + excuse + '\n\n'
        if len(youtube_id) > 0:
            email_body += 'Youtube URL : https://www.youtube.com/watch?v=' + youtube_id + '\n\n'
        if v1.upload_filename is not None:
            email_body += 'Filename : ' + v1.upload_filename + '\n'
        email_body += 'Upload Date : ' + str(v1.upload_date) + '(UTC)\n'
        email_body += 'Course Title (optional) : ' + v1.client_information + '\n'
        email_body += 'edX Studio Course URL : ' + v1.edx_studio_url + '\n\n'
        email_body += 'Please do not reply to this email.\n\n <<EOM'

        conn = boto.ses.connect_to_region('us-east-1')

        conn.send_email(
            auth_dict['veda_noreply_email'],
            email_subject,
            email_body,
            [v1.status_email, auth_dict['admin_email']]
        )


if __name__ == '__main__':
    report_status(status='Complete', abvid_serial="5c34a85e5f", youtube_id='TEST')
