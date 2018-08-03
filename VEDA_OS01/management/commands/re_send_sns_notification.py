"""
Management command used to mimic a SNS notification, which
calls the api/ingest_from_s3 HTTP endpoint, in the case that
SNS is no longer sending notifications for that video, and
they remain in the 'unprocessed' prefix.

Takes either a studio upload ID (a valid key in s3) and just
processes that video, or a date (in the format year-month-day)
and processes all videos that were last modified before that date.

Usage:
python manage.py re_send_sns_notification --date=2018-08-03
python manage.py re_send_sns_notification --key=12345678-1234-1234-1234-123456789abc
"""
import logging
import boto
import boto.s3
from datetime import datetime
import requests

from django.core.management.base import BaseCommand, CommandError

from VEDA.utils import get_config

try:
    boto.config.add_section('Boto')
except:
    pass

LOGGER = logging.getLogger(__name__)
CONFIG_DATA = get_config()


class Command(BaseCommand):
    """
    Re-send SNS notification command class
    """
    help = 'Re-send SNS notification to api/ingest_from_s3. Takes either a studio upload ID or a date.'

    def add_arguments(self, parser):
        super(Command, self).add_arguments(parser)

        parser.add_argument(
            '-d',
            '--date',
            help="Process all videos in the s3 bucket before this date, in the format year-month-day (eg.2018-08-03)"
        )

        parser.add_argument(
            '-k',
            '--key',
            help="Process just the video with this s3 key (a studio upload ID)."
        )

    def handle(self, *args, **options):
        """
        handle method for command class.
        """
        LOGGER.info('[Re-send SNS notification] Process started.')

        key = options.get('key')
        date = options.get('date')

        if key and date:
            raise CommandError('Cannot pass in both an ID and a date.')
        elif key:
            bucket = self.connect_boto()

            if bucket.get_key(CONFIG_DATA['edx_s3_ingest_prefix'] + key):
                self.send_http_request(key)
            else:
                raise CommandError('Specified key cannot be found in s3.')
        elif date:
            bucket = self.connect_boto()

            try:
                cutoff_date = datetime.strptime(date, '%Y-%m-%d')
            except AttributeError:
                raise CommandError('Incorrect formatting. Date should be formatted like year-month-day.')

            keys = list(bucket.list(CONFIG_DATA['edx_s3_ingest_prefix']))

            for key in keys:
                last_modified_date = datetime.strptime(key.last_modified, '%Y-%m-%dT%X.000Z')
                if last_modified_date < cutoff_date:
                    self.send_http_request(key.name)

    def send_http_request(self, key):
        data = '{"Type" : "Notification", "Subject" : "",'
        data += '"Message" : "{\\"Records\\":[{\\"s3\\":{\\"object\\":{\\"key\\":\\"' + key + '\\"}}}]}"}'

        headers = {
            'Connection': 'Keep-Alive',
            'Content-Type': 'text/plain; charset=UTF-8',
            'x-amz-sns-message-type': 'Notification'
        }

        url = 'https://veda.edx.org/api/ingest_from_s3/'
        r = requests.post(url, headers=headers, data=data)

        LOGGER.info('Ingest from S3 API call sent for for {} with status code {}'.format(key, r.status_code))

    def connect_boto(self):
        conn = boto.connect_s3()
        
        return conn.get_bucket(CONFIG_DATA['edx_s3_ingest_bucket'])