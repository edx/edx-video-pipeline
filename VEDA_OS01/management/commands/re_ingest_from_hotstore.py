"""
Management command used to re-ingest video from hotstore based on the params provided.
"""
import logging
import boto
import boto.s3

from django.core.management.base import BaseCommand

from VEDA_OS01.models import Video
from control.veda_file_discovery import feed_to_ingest

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
            feed_to_ingest(keyname, bucket)
            LOGGER.info('Ingest completed for {}'.format(vd.edx_id))
