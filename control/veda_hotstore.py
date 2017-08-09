
import boto
import os
import shutil
import sys
import yaml

import boto.s3
from boto.s3.key import Key
from boto.exception import S3ResponseError
import newrelic.agent
from os.path import expanduser

from veda_utils import ErrorObject

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
homedir = expanduser("~")


class Hotstore(object):
    """
    Upload file to hotstore (short term storage, s3 objects)

    """
    def __init__(self, video_proto, upload_filepath, **kwargs):
        self.video_proto = video_proto
        self.upload_filepath = upload_filepath
        # is this a final/encode file?
        self.endpoint = kwargs.get('endpoint', False)

        self.auth_yaml = kwargs.get(
            'auth_yaml',
            os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                'instance_config.yaml'
            ),
        )
        self.auth_dict = self._READ_AUTH()
        self.endpoint_url = None

    def _READ_AUTH(self):
        if self.auth_yaml is None:
            return None
        if not os.path.exists(self.auth_yaml):
            return None

        with open(self.auth_yaml, 'r') as stream:
            try:
                auth_dict = yaml.load(stream)
                return auth_dict
            except yaml.YAMLError as exc:
                return None

    @newrelic.agent.background_task()
    def upload(self):
        if self.auth_dict is None:
            return False

        if not os.path.exists(self.upload_filepath):
            ErrorObject().print_error(
                message='Hotstore: File Not Found'
            )
            return False

        self.upload_filesize = os.stat(self.upload_filepath).st_size

        if self.upload_filesize < self.auth_dict['multi_upload_barrier']:
            return self._BOTO_SINGLEPART()
        else:
            return self._BOTO_MULTIPART()

    def _BOTO_SINGLEPART(self):
        """
        Upload single part (under threshold in instance_auth)
        self.auth_dict['multi_upload_barrier']
        """
        if self.endpoint is False:
            try:
                conn = boto.connect_s3()
                delv_bucket = conn.get_bucket(
                    self.auth_dict['veda_s3_hotstore_bucket']
                )
            except S3ResponseError:
                ErrorObject().print_error(
                    message='Hotstore: Bucket Connectivity'
                )
                return False
        else:
            try:
                conn = boto.connect_s3()
                delv_bucket = conn.get_bucket(
                    self.auth_dict['edx_s3_endpoint_bucket']
                )
            except S3ResponseError:
                ErrorObject().print_error(
                    message='Endpoint: Bucket Connectivity'
                )
                return False

        upload_key = Key(delv_bucket)
        upload_key.key = '.'.join((
            self.video_proto.veda_id,
            self.upload_filepath.split('.')[-1]
        ))
        try:
            upload_key.set_contents_from_filename(self.upload_filepath)
            return True
        except:
            upload_key.set_contents_from_filename(self.upload_filepath)
            return True

    def _BOTO_MULTIPART(self):
        """
        Split file into chunks, upload chunks

        NOTE: this should never happen, as your files should be much
        smaller than this, but one never knows
        """
        path_to_multipart = os.path.dirname(self.upload_filepath)
        filename = os.path.basename(self.upload_filepath)
        """
        This is modular
        """
        if not os.path.exists(os.path.join(path_to_multipart, filename.split('.')[0])):
            os.mkdir(os.path.join(path_to_multipart, filename.split('.')[0]))

        os.chdir(os.path.join(path_to_multipart, filename.split('.')[0]))
        """
        Split File into chunks
        """
        split_command = 'split -b10m -a5'  # 5 part names of 5mb
        sys.stdout.write('%s : %s\n' % (filename, 'Generating Multipart'))
        os.system(' '.join((split_command, self.upload_filepath)))
        sys.stdout.flush()

        """
        Connect to s3
        """
        if self.endpoint is False:
            try:
                c = boto.connect_s3()
                b = c.lookup(self.auth_dict['veda_s3_hotstore_bucket'])
            except S3ResponseError:
                ErrorObject().print_error(
                    message='Hotstore: Bucket Connectivity'
                )
                return False
        else:
            try:
                c = boto.connect_s3()
                b = c.lookup(self.auth_dict['edx_s3_endpoint_bucket'])
            except S3ResponseError:
                ErrorObject().print_error(
                    message='Endpoint: Bucket Connectivity'
                )
                return False

        if b is None:
            ErrorObject().print_error(
                message='Deliverable Fail: s3 Bucket Error'
            )
            return False

        """
        Upload and stitch parts // with a decent display
        """
        mp = b.initiate_multipart_upload(
            '.'.join((
                self.video_proto.veda_id,
                filename.split('.')[-1]
            ))
        )

        x = 1
        for file in sorted(os.listdir(
            os.path.join(
                path_to_multipart,
                filename.split('.')[0]
            )
        )):
            sys.stdout.write('%s : %s\r' % (file, 'uploading part'))
            fp = open(file, 'rb')
            mp.upload_part_from_file(fp, x)
            fp.close()
            sys.stdout.flush()
            x += 1
        sys.stdout.write('\n')
        mp.complete_upload()

        """
        Clean up multipart
        """
        os.chdir(homedir)
        shutil.rmtree(os.path.join(path_to_multipart, filename.split('.')[0]))
        return True


def main():
    pass


if __name__ == '__main__':
    sys.exit(main())
