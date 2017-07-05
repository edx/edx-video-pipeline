
import os.path
import boto
import yaml
from boto.s3.connection import S3Connection
import newrelic.agent

try:
    boto.config.add_section('Boto')
except:
    pass
boto.config.set('Boto', 'http_socket_timeout', '100')

newrelic.agent.initialize(
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'veda_newrelic.ini'
    )
)
"""
multi-point videofile discovery
Currently:
    FTP
    Amazon S3 (studio-ingest as well as about/marketing
        video ingest
        )
    Local (watchfolder w/o edit priv.)

"""
from control_env import *
from veda_utils import ErrorObject
from veda_file_ingest import VideoProto, VedaIngest
from veda_val import VALAPICall


class FileDiscovery():

    def __init__(self, **kwargs):
        self.video_info = {}

        self.auth_dict = {}
        self.auth_yaml = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            'veda_auth.yaml'
        )
        with open(self.auth_yaml, 'r') as stream:
            try:
                self.auth_dict = yaml.load(stream)
            except yaml.YAMLError as exc:
                pass

        self.bucket = None
        """
        FTP Server Vars
        """
        self.ftp_key = None
        self.ftp_follow_delay = str(5000)
        self.ftp_log = "/Users/Shared/edX1/LG/Transfers.log"
        self.wfm_log = "/Users/Shared/edX1/LG/WFM.log"
        self.ftp_faillog = "/Users/Shared/edX1/LG/FailedTransfers.log"
        self.node_work_directory = kwargs.get('node_work_directory', WORK_DIRECTORY)

    @newrelic.agent.background_task()
    def about_video_ingest(self):
        if self.node_work_directory is None:
            ErrorObject().print_error(
                message='No Workdir'
            )
            return None
        """
        Crawl ingest bucket looking for files
        """
        conn = S3Connection(
            self.auth_dict['veda_access_key_id'],
            self.auth_dict['veda_secret_access_key']
        )

        """
        Occassional s3 Error
        """
        try:
            self.bucket = conn.get_bucket(self.auth_dict['veda_s3_upload_bucket'])
        except:
            return None

        for key in self.bucket.list('upload/', '/'):
            meta = self.bucket.get_key(key.name)
            if meta.name != 'upload/':
                self.about_video_validate(
                    meta=meta,
                    key=key
                )

    def about_video_validate(self, meta, key):
        abvid_serial = meta.name.split('/')[1]
        upload_query = VedaUpload.objects.filter(
            video_serial=meta.name.split('/')[1]
        )
        if len(upload_query) == 0:
            '''
            Non serialized upload - reject
            '''
            return None

        if upload_query[0].upload_filename is not None:
            file_extension = upload_query[0].upload_filename.split('.')[-1]
        else:
            upload_query[0].upload_filename = 'null_file_name.mp4'
            file_extension = 'mp4'

        if len(file_extension) > 4:
            file_extension = ''

        meta.get_contents_to_filename(
            os.path.join(
                self.node_work_directory,
                upload_query[0].upload_filename
            )
        )

        course_query = Course.objects.get(institution='EDX', edx_classid='ABVID')
        """
        Trigger Ingest Process
        """
        V = VideoProto(
            abvid_serial=abvid_serial,
            client_title=upload_query[0].upload_filename.replace('.' + file_extension, ''),
            file_extension=file_extension,
        )

        I = VedaIngest(
            course_object=course_query,
            video_proto=V,
            node_work_directory=self.node_work_directory
        )
        I.insert()

        """
        Move Key out of 'upload' folder
        """
        new_key = '/'.join(('process', meta.name.split('/')[1]))
        key.copy(self.bucket, new_key)
        key.delete()

        reset_queries()

    @newrelic.agent.background_task()
    def studio_s3_ingest(self):
        if self.node_work_directory is None:
            ErrorObject().print_error(
                message='No Workdir'
            )
            return None

        """
        Ingest files from studio upload endpoint
        """
        conn = S3Connection(
            self.auth_dict['edx_access_key_id'],
            self.auth_dict['edx_secret_access_key']
        )

        """Occassional s3 Error"""
        try:
            self.bucket = conn.get_bucket(self.auth_dict['edx_s3_ingest_bucket'])
        except:
            print 'S3: Ingest Conn Failure'
            return None

        for key in self.bucket.list('prod-edx/unprocessed/', '/'):
            meta = self.bucket.get_key(key.name)
            self.studio_s3_validate(
                meta=meta,
                key=key
            )

    def studio_s3_validate(self, meta, key):

        if meta.get_metadata('course_video_upload_token') is None:
            return None

        client_title = meta.get_metadata('client_video_id')
        course_hex = meta.get_metadata('course_video_upload_token')
        course_url = meta.get_metadata('course_key')
        edx_filename = key.name[::-1].split('/')[0][::-1]

        if len(course_hex) == 0:
            return None

        course_query = Course.objects.filter(studio_hex=course_hex)
        if len(course_query) == 0:
            V = VideoProto(
                s3_filename=edx_filename,
                client_title=client_title,
                file_extension='',
                platform_course_url=course_url
            )

            """
            Call VAL Api
            """
            val_status = 'invalid_token'
            VAC = VALAPICall(
                video_proto=V,
                val_status=val_status
            )
            VAC.call()

            new_key = 'prod-edx/rejected/' + key.name[::-1].split('/')[0][::-1]
            key.copy(self.bucket, new_key)
            key.delete()
            return None

        file_extension = client_title[::-1].split('.')[0][::-1]

        """
        download file
        """
        if len(file_extension) == 3:
            try:
                meta.get_contents_to_filename(
                    os.path.join(
                        self.node_work_directory,
                        edx_filename + '.' + file_extension
                    )
                )
                file_ingested = True
            except:
                print 'File Copy Fail: Studio S3 Ingest'
                file_ingested = False
        else:
            try:
                meta.get_contents_to_filename(
                    os.path.join(
                        self.node_work_directory,
                        edx_filename
                    )
                )
                file_ingested = True
            except:
                print 'File Copy Fail: Studio S3 Ingest'
                file_ingested = False
                file_extension = ''

        if file_ingested is not True:
            # 's3 Bucket ingest Fail'
            new_key = 'prod-edx/rejected/' + key.name[::-1].split('/')[0][::-1]
            try:
                key.copy(self.bucket, new_key)
            except:
                key.copy(self.bucket, new_key)
            key.delete()
            return None

        """
        Trigger Ingest Process
        """
        V = VideoProto(
            s3_filename=edx_filename,
            client_title=client_title,
            file_extension=file_extension,
            platform_course_url=course_url
        )

        I = VedaIngest(
            course_object=course_query[0],
            video_proto=V,
            node_work_directory=self.node_work_directory
        )
        I.insert()

        if I.complete is False:
            return None

        """
        Delete Original After Copy
        """
        new_key = 'prod-edx/processed/' + key.name[::-1].split('/')[0][::-1]
        try:
            key.copy(self.bucket, new_key)
        except:
            key.copy(self.bucket, new_key)
        # key.copy(self.bucket, new_key)
        key.delete()


def main():
    pass


if __name__ == '__main__':
    sys.exit(main())
