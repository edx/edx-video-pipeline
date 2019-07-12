"""
Tests of the create_oauth_client management command.
"""

from __future__ import absolute_import
from itertools import product

import ddt
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from oauth2_provider.models import Application
from VEDA_OS01.management.commands.create_oauth_client import CLIENT_TYPES, GRANT_TYPES
from six.moves import zip


USER_ID = 1
USERNAME = 'username'
CLIENT_ID = 'cliend_id101'
REDIRECT_URI = 'https://www.example.com/o/token'

OPTIONAL_COMMAND_ARGS = ('username', 'redirect_uris', 'client_name', 'client_secret', 'skip_authorization')


@ddt.ddt
class CreateOauthAppClientTests(TestCase):
    """
    Management command test class.
    """
    def setUp(self):
        super(CreateOauthAppClientTests, self).setUp()
        user_model = get_user_model()
        self.user = user_model.objects.create(username=USERNAME)

    def _call_command(self, args, options=None):
        """
        Call the command.
        """
        if options is None:
            options = {}

        call_command('create_oauth_client', *args, **options)

    def assert_client_created(self, args, options):
        """
        Verify that the Client was created.
        """
        application = Application.objects.get()

        for index, attr in enumerate(('client_id', 'client_type', 'authorization_grant_type')):
            self.assertEqual(args[index], getattr(application, attr))

        username = options.get('username')
        if username is not None:
            get_user_model().objects.get(username=username)

        client_name = options.get('client_name')
        if client_name is not None:
            self.assertEqual(client_name, application.name)

        for attr in ('client_secret', 'redirect_uris', 'skip_authorization'):
            value = options.get(attr)
            if value is not None:
                self.assertEqual(value, getattr(application, attr))

    # Generate all valid argument and options combinations
    @ddt.data(*product(
        # Generate all valid argument combinations
        product(
            (CLIENT_ID,),
            (t for t in CLIENT_TYPES),
            (g for g in GRANT_TYPES),
        ),
        # Generate all valid option combinations
        (dict(list(zip(OPTIONAL_COMMAND_ARGS, p))) for p in product(
            (USERNAME, None),
            (REDIRECT_URI, None),
            ('client_name', None),
            ('client_secret', None),
            (True, False)
        )
        )
    ))
    @ddt.unpack
    def test_client_creation(self, args, options):
        """
        Verify that the command creates a Client when given valid arguments and options.
        """
        self._call_command(args, options)
        self.assert_client_created(args, options)

    @ddt.data(
        ((CLIENT_ID,), 'too few arguments'),
        ((CLIENT_ID, REDIRECT_URI, CLIENT_TYPES[0], CLIENT_TYPES[1]), 'unrecognized arguments'),
    )
    @ddt.unpack
    def test_argument_cardinality(self, args, err_msg):
        """
        Verify that the command fails when given an incorrect number of arguments.
        """
        with self.assertRaises(CommandError) as exc:
            self._call_command(args, {})

        self.assertIn(err_msg, exc.exception.message)

    @ddt.data(
        {
            'client_id': '',
        },
        {
            'client_id': '    ',
        },
        {
            'client_id': None,
        }
    )
    @ddt.unpack
    def test_client_id_validation(self, client_id):
        """
        Verify that the command fails when the provided client id is invalid.
        """
        with self.assertRaises(CommandError) as exc:
            self._call_command((client_id, CLIENT_TYPES[0], GRANT_TYPES[0]))

        self.assertEqual(
            'Client id provided is invalid.',
            exc.exception.message
        )

    def test_client_type_validation(self):
        """
        Verify that the command fails when the provided client type is invalid.
        """
        with self.assertRaises(CommandError) as exc:
            self._call_command((CLIENT_ID, 'invalid_client_type', GRANT_TYPES[0]))

        self.assertEqual(
            'Client type provided is invalid. Please use one of {}.'.format(CLIENT_TYPES),
            exc.exception.message
        )

    def test_grant_type_validation(self):
        """
        Verify that the command fails when the provided grant type is invalid.
        """
        with self.assertRaises(CommandError) as exc:
            self._call_command((CLIENT_ID, CLIENT_TYPES[0], 'invalid_grant_type'))

        self.assertEqual(
            'Grant type provided is invalid. Please use one of {}.'.format(GRANT_TYPES),
            exc.exception.message
        )

    def test_username_validation(self):
        """
        Verify that the command fails when the provided username is invalid.
        """
        with self.assertRaises(CommandError) as exc:
            self._call_command(
                (CLIENT_ID, CLIENT_TYPES[0], GRANT_TYPES[0]),
                {'username': 'invalid'}
            )

        self.assertEqual(
            'User matching the provided username does not exist.',
            exc.exception.message
        )

    def test_url_validation(self):
        """
        Verify that the command fails when the provided URLs are invalid.
        """
        args = CLIENT_ID, CLIENT_TYPES[0], GRANT_TYPES[0]
        with self.assertRaises(CommandError) as exc:
            self._call_command(args, {'redirect_uris': 'invalide uri'})

        self.assertEqual(
            'URIs provided are invalid. Please provide valid redirect URIs.',
            exc.exception.message
        )

    def test_idempotency(self):
        """
        Verify that the command can be run repeatedly with the same client id, without any ill effects.
        """
        args = [CLIENT_ID, CLIENT_TYPES[0], GRANT_TYPES[0]]
        options = {
            'username': 'username',
            'client_secret': 'client_secret',
            'client_name': 'client_name',
            'redirect_uris': 'https://www.example.com/o/token',
            'skip_authorization': True
        }

        self._call_command(args, options)
        self.assert_client_created(args, options)

        # Verify that the command is idempotent.
        self._call_command(args, options)
        self.assert_client_created(args, options)

        # Verify that attributes are updated if the command is run with the same client ID,
        # but with other options varying.
        options['client_secret'] = 'another-secret'
        options['skip_authorization'] = False
        self._call_command(args, options)
        self.assert_client_created(args, options)
