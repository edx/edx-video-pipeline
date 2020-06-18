"""
Management command used to re-encrypt transcript credentials data with new fernet key.
"""

import logging

from cryptography.fernet import InvalidToken
from django.core.management.base import BaseCommand
from django.db import transaction

from VEDA_OS01.models import TranscriptCredentials
from VEDA_OS01.utils import invalidate_fernet_cached_properties


LOGGER = logging.getLogger(__name__)


class Command(BaseCommand):
    """
    Re-encrypt trancript credentials command class.
    """
    help = 'Re-encrypts transcript credentials with new fernet key.'

    def handle(self, *args, **options):
        """
        handle method for command class.
        """

        LOGGER.info('[Transcript credentials re-encryption] Process started.')

        # Invalidate cached properties so that we get the latest keys
        invalidate_fernet_cached_properties(TranscriptCredentials, ['api_key', 'api_secret'])

        try:
            with transaction.atomic():
                # Call save on each credentials record so that re-encryption can be be performed on fernet fields.
                for transcript_credential in TranscriptCredentials.objects.all():
                    transcript_credential.save()

            LOGGER.info('[Transcript credentials re-encryption] Process completed.')

        except InvalidToken:
            LOGGER.exception(
                '[Transcript credentials re-encryption] No valid fernet key present to decrypt. Process halted.'
            )
