"""
Management command used to create an OAuth client in the database.
"""


from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import URLValidator
from oauth2_provider.models import Application

CLIENT_TYPES = [client_type[0] for client_type in Application.CLIENT_TYPES]
GRANT_TYPES = [grant_type[0] for grant_type in Application.GRANT_TYPES]


class Command(BaseCommand):
    """
    create_oauth_client command class
    """
    help = 'Create a new OAuth Application Client. Outputs a serialized representation of the newly-created Client.'

    def add_arguments(self, parser):
        super(Command, self).add_arguments(parser)

        # Required positional arguments.
        parser.add_argument(
            'client_id',
            help="String to assign as the Client ID."
        )
        parser.add_argument(
            'client_type',
            help="Client type."
        )
        parser.add_argument(
            'authorization_grant_type',
            help="Authorization flows available to the Application."
        )

        # Optional options.
        parser.add_argument(
            '-u',
            '--username',
            help="Username of a user to associate with the Client."
        )
        parser.add_argument(
            '-r',
            '--redirect_uris',
            help="Comma separated redirect URIs."
        )
        parser.add_argument(
            '-n',
            '--client_name',
            help="String to assign as the Client name."
        )
        parser.add_argument(
            '-s',
            '--client_secret',
            help="String to assign as the Client secret. Should not be shared."
        )
        parser.add_argument(
            '-a',
            '--skip_authorization',
            action='store_true',
            default=False,
            help="Skip authorization for trusted applications."
        )

    def handle(self, *args, **options):
        self._clean_required_args(options['client_id'], options['client_type'], options['authorization_grant_type'])
        self._parse_options(options)

        # Check if client ID is already in use. If so, fetch existing Client and update fields.
        Application.objects.update_or_create(
            client_id=self.fields.pop('client_id'), defaults=self.fields
        )

    def _clean_required_args(self, client_id, client_type, grant_type):
        """
        Validate and clean the command's arguments.

        Arguments:
            client_id (str): Client Id.
            client_type (str): Client Type.
            grant_type (str): Grant Type

        Raises:
            CommandError, if the arguments have invalid values.
        """
        client_id = client_id and client_id.strip()
        if not client_id:
            raise CommandError('Client id provided is invalid.')

        client_type = client_type.lower()
        if client_type not in CLIENT_TYPES:
            raise CommandError('Client type provided is invalid. Please use one of {}.'.format(CLIENT_TYPES))

        grant_type = grant_type.lower()
        if grant_type not in GRANT_TYPES:
            raise CommandError('Grant type provided is invalid. Please use one of {}.'.format(GRANT_TYPES))

        self.fields = {  # pylint: disable=attribute-defined-outside-init
            'client_id': client_id,
            'client_type': client_type,
            'authorization_grant_type': grant_type,
        }

    def _parse_options(self, options):
        """
        Parse the command's options.

        Arguments:
            options (dict): Options with which the command was called.

        Raises:
            CommandError, if user does not exist or redirect_uris is invalid
        """
        for key in ('username', 'client_name', 'client_secret', 'redirect_uris', 'skip_authorization'):
            value = options.get(key)

            # replace argument names to match Application model field names
            if key == 'username':
                key = 'user_id'
            elif key == 'client_name':
                key = 'name'

            if value is not None:
                self.fields[key] = value

        username = self.fields.get('user_id')
        if username is not None:
            try:
                user_model = get_user_model()
                self.fields['user_id'] = user_model.objects.get(username=username).id
            except user_model.DoesNotExist:
                raise CommandError('User matching the provided username does not exist.')

        uris = self.fields.get('redirect_uris')
        if uris is not None:
            uris = uris.split(',')
            for uri in uris:
                try:
                    URLValidator()(uri)
                except ValidationError:
                    raise CommandError('URIs provided are invalid. Please provide valid redirect URIs.')
