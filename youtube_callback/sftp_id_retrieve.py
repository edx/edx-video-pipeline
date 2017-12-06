"""
Check SFTP dropboxes for YT Video ID XML information

"""
import datetime
import fnmatch
import os
import shutil
import sys
import xml.etree.ElementTree as ET
from datetime import timedelta
from os.path import expanduser

import django
import pysftp
from django.utils.timezone import utc

from control.veda_utils import ErrorObject, Metadata, VideoProto
from control.veda_val import VALAPICall
from frontend.abvid_reporting import report_status
from VEDA_OS01.models import URL, Encode, Video
from youtube_callback.daemon import get_course

project_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_path not in sys.path:
    sys.path.append(project_path)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'VEDA.settings.local')
django.setup()


"""
Defaults:
"""
homedir = expanduser("~")
workdir = os.path.join(homedir, 'download_data_holding')
YOUTUBE_LOOKBACK_DAYS = 4


def callfunction(course):
    """

    :param course:
    :return:
    """
    if os.path.exists(workdir):
        shutil.rmtree(workdir)
    os.mkdir(workdir)

    xml_downloader(course)

    for file in os.listdir(workdir):
        print file
        upload_data = domxml_parser(file)

        if upload_data is not None:
            print upload_data
            urlpatch(upload_data)


def xml_downloader(course):
    """

    :param course:
    :return:
    """

    private_key = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        'static_files',
        'youtubekey'
    )

    cnopts = pysftp.CnOpts()
    cnopts.hostkeys = None

    with pysftp.Connection(
        'partnerupload.google.com',
        username=course.yt_logon,
        private_key=private_key,
        port=19321,
        cnopts=cnopts
    ) as s1:
        s1.timeout = 60.0
        for d in s1.listdir_attr():
            crawl_sftp(d=d, s1=s1)


def crawl_sftp(d, s1):
    """
    crawl the sftp dir and dl the XML files for parsing

    :param d: directory
    :param s1: sftp connection
    :return: None
    """
    dirtime = datetime.datetime.fromtimestamp(d.st_mtime)
    if dirtime < datetime.datetime.now() - timedelta(days=YOUTUBE_LOOKBACK_DAYS):
        return None
    if d.filename == "files_to_be_removed.txt":
        return None
    if d.filename == 'FAILED':
        return None
    try:
        s1.cwd(d.filename)
    except:
        return None

    for f in s1.listdir_attr():
        filetime = datetime.datetime.fromtimestamp(f.st_mtime)
        if not filetime > datetime.datetime.now() - timedelta(days=YOUTUBE_LOOKBACK_DAYS):
            continue
        if fnmatch.fnmatch(f.filename, '*.xml') or fnmatch.fnmatch(f.filename, '*.csv'):
            # Determine If there are extant downloaded status files for this same ID,
            # If yes, increment filename
            x = 0
            while True:
                """
                Just in case something runs out
                """
                if x > 20:
                    break
                file_to_find = f.filename.split('.')[0] + \
                    str(x) + \
                    '.' + \
                    f.filename.split('.')[1]
                if os.path.exists(os.path.join(workdir, file_to_find)):
                    x += 1
                else:
                    break
            print "%s : %s" % (f.filename, file_to_find)
            s1.get(
                f.filename,
                os.path.join(workdir, file_to_find)
            )
    s1.cwd('..')


def domxml_parser(file):
    """

    :param file:
    :return:
    """

    if 'status-' not in file:
        return

    upload_data = {
        'datetime': None,
        'status': None,
        'duplicate_url': None,
        'edx_id': file.strip('status-').split('_')[0],
        'file_suffix': None,
        'youtube_id': None
    }
    try:
        tree = ET.parse(os.path.join(workdir, file))
    except ET.ParseError:
        return
    except IOError:
        return
    root = tree.getroot()
    for child in root:

        if child.tag == 'timestamp':
            upload_data['datetime'] = datetime.datetime.strptime(
                child.text,
                '%Y-%m-%dT%H:%M:%S'
            ).replace(tzinfo=utc)

        elif child.tag == 'action':
            if child.get('name') == 'Process file':
                for c in child:
                    if c.tag == 'status_detail':
                        if c.text == 'The file size cannot be zero.':
                            return None

                    if c.tag == 'action':
                        if c.get('name') == 'Submit video':
                            for d in c:

                                if d.tag == 'status':
                                    upload_data['status'] = d.text

                                elif d.tag == 'status_detail':
                                    if d.text != 'Live!':
                                        if 'duplicate upload' in d.text:
                                            upload_data['duplicate_url'] = d.text[::-1].split(' ')[0][::-1].split('.')[0]  # nopep8 TODO: refactor to fix
                                            upload_data['status'] = 'Duplicate'

                                elif d.tag == 'in_file':
                                    try:
                                        upload_data['file_suffix'] = d.text.split('\'')[1].split('_')[1].split('.')[0]  # nopep8
                                    except IndexError:
                                        upload_data['file_suffix'] = '100'
                                elif d.tag == 'id':
                                    upload_data['youtube_id'] = d.text
    return upload_data


def urlpatch(upload_data):
    """

    # :param upload_data: dict
    # :return:
    """
    if upload_data['status'] == 'Failure':
        return None
    try:
        test_id = Video.objects.filter(edx_id=upload_data['edx_id']).latest()
    except:
        upload_data['status'] = 'Failure'

    if upload_data['status'] == 'Success':
        url_query = URL.objects.filter(
            encode_url=upload_data['youtube_id']
        )

        if len(url_query) == 0:
            u1 = URL(
                videoID=Video.objects.filter(
                    edx_id=test_id.edx_id
                ).latest()
            )
            u1.encode_profile = Encode.objects.get(
                encode_suffix=upload_data['file_suffix']
            )
            u1.encode_url = upload_data['youtube_id']
            u1.url_date = upload_data['datetime']
            u1.encode_duration = test_id.video_orig_duration
            u1.encode_bitdepth = 0
            u1.encode_size = 0
            u1.save()

            """
            Report to Email

            """
            if 'EDXABVID' in upload_data['edx_id']:
                v1 = Video.objects.filter(edx_id=upload_data['edx_id']).latest()
                if v1.abvid_serial is not None:

                    report_status(
                        status="Complete",
                        abvid_serial=v1.abvid_serial,
                        youtube_id=upload_data['youtube_id']
                    )

        video_check = Video.objects.filter(edx_id=test_id.edx_id).latest()

        if video_check.video_trans_status == 'Youtube Duplicate':
            Video.objects.filter(
                edx_id=video_check.edx_id
            ).update(
                video_trans_status='Progress'
            )

        """
        Update Status & VAL
        """
        video_proto = VideoProto(
            veda_id=test_id.edx_id,
            val_id=test_id.studio_id,
            client_title=test_id.client_title,
            duration=test_id.video_orig_duration,
            bitrate='0',
            s3_filename=test_id.studio_id
        )
        print test_id.video_orig_duration
        VF = Metadata(
            video_object=test_id
        )

        encode_list = VF._FAULT(
            video_object=test_id
        )

        """
        Review can stop here
        """
        if upload_data['file_suffix'] == 'RVW':
            return None

        if len(encode_list) == 0:
            Video.objects.filter(edx_id=upload_data['edx_id']).update(video_trans_status='Complete')
            val_status = 'file_complete'
        else:
            val_status = 'transcode_active'

        ApiConn = VALAPICall(
            video_proto=video_proto,
            val_status=val_status,
            endpoint_url=upload_data['youtube_id'],
            encode_profile='youtube'
        )
        ApiConn.call()

    elif upload_data['status'] == 'Duplicate' and \
            upload_data['file_suffix'] == '100':

        url_query = URL.objects.filter(
            videoID=Video.objects.filter(
                edx_id=upload_data['edx_id']
            ).latest(),
            encode_profile=Encode.objects.get(
                encode_suffix=upload_data['file_suffix']
            )
        )
        if len(url_query) == 0:

            if 'EDXABVID' in upload_data['edx_id']:
                report_status(
                    status="Youtube Duplicate",
                    abvid_serial=test_id.abvid_serial,
                    youtube_id=''
                )

            Video.objects.filter(edx_id=upload_data['edx_id']).update(video_trans_status='Youtube Duplicate')
            video_proto = VideoProto(
                veda_id=test_id.edx_id,
                val_id=test_id.studio_id,
                client_title=test_id.client_title,
                duration=test_id.video_orig_duration,
                bitrate='0',
                s3_filename=test_id.studio_id
            )
            ApiConn = VALAPICall(
                video_proto=video_proto,
                val_status="duplicate",
                endpoint_url="DUPLICATE",
                encode_profile='youtube'
            )
            ApiConn.call()
