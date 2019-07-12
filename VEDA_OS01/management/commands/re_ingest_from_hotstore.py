"""
Management command used to re-ingest video from hotstore based on the params provided.
"""
from __future__ import absolute_import
import logging
import boto
import boto.s3
import os
import subprocess

from django.core.management.base import BaseCommand

from VEDA_OS01.models import Video
from control.veda_file_discovery import FileDiscovery

try:
    boto.config.add_section('Boto')
except:
    pass

LOGGER = logging.getLogger(__name__)
BUCKET_NAME = 'veda-hotstore'

class Command(BaseCommand):
    """
    Re-ingest video from hotstore command class
    """
    help = 'Re-ingest video from in VEDA S3 bucket (hotstore)'

    def add_arguments(self, parser):
        super(Command, self).add_arguments(parser)

        # Required positional arguments.
        parser.add_argument(
            'start_video_id',
            help="The smaller video id for the list"
        )
        parser.add_argument(
            'end_video_id',
            help="The bigger video id for the list"
        )


    def handle(self, *args, **options):
        """
        handle method for command class.
        """

        LOGGER.info('[Re-ingest from hotstore] Process started.')
    
        start_id = options.get('start_video_id')
        end_id = options.get('end_video_id')
        query = Video.objects.filter(id__range=(start_id, end_id))
        
        conn = boto.connect_s3()
        bucket = conn.get_bucket(BUCKET_NAME)
        for vd in query:
            keyname = vd.edx_id + '.' + vd.video_orig_extension
            filename = './' + keyname
            vd_key = bucket.get_key(keyname)
            file_discovery = FileDiscovery()  
            file_discovery.validate_metadata_and_feed_to_ingest(vd_key)
            LOGGER.info('Ingest completed for {}'.format(vd.edx_id))
