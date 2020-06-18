"""
Tests common utils
"""

import glob
import os
import shutil
import tempfile
from unittest import TestCase

import six.moves.urllib.parse
import yaml
from ddt import data, ddt, unpack
from mock import MagicMock, Mock, patch

from VEDA import utils
from six.moves import range

TEST_CONFIG = {
    'var1': 123,
    'var2': 999,
    'sub': {
        'sub_var': 'http://example.com'
    }
}

TEST_STATIC_CONFIG = {
    'abc': 999,
    'nested': {
        'nested_url': 'nested.example.com'
    }
}


@ddt
class UtilTests(TestCase):
    """
    Common util tests.
    """
    def setUp(self):
        """
        Tests setup.
        """
        self._orig_environ = dict(os.environ)

        # create a temporary default config file
        _, self.file_path = tempfile.mkstemp(
            suffix='.yml',
            dir=tempfile.tempdir
        )
        with open(self.file_path, 'w') as outfile:
            yaml.dump(TEST_CONFIG, outfile, default_flow_style=False)

        os.environ['VIDEO_PIPELINE_CFG'] = self.file_path

        # create a temporary static config file
        _, self.static_file_path = tempfile.mkstemp(
            suffix='.yml',
            dir=tempfile.tempdir
        )
        with open(self.static_file_path, 'w') as outfile:
            yaml.dump(TEST_STATIC_CONFIG, outfile, default_flow_style=False)

    def tearDown(self):
        """
        Reverse the setup
        """
        # Reset Environment back to original state
        os.environ.clear()
        os.environ.update(self._orig_environ)

        # remove temporary files
        os.remove(self.file_path)
        os.remove(self.static_file_path)

    @data(
        {
            'urls': ('http://api.cielo24/', '/add/job'),
            'params': {}
        },
        {
            'urls': ('http://api.cielo24', '/add/job'),
            'params': {'a': '1', 'b': '2'}
        },
        {
            'urls': ('http://api.cielo24/', 'add/job'),
            'params': {'c': '3', 'd': '4'}
        },
        {
            'urls': ('http://api.cielo24', 'add/job'),
            'params': {'p': '100'}
        },
        {
            'urls': ('http://api.cielo24', 'add/job', 'media'),
            'params': {'p': '100'}
        }
    )
    @unpack
    def test_build_url(self, urls, params):
        """
        Tests that utils.build_url works as expected.
        """
        url = utils.build_url(
            *urls,
            **params
        )
        parsed = six.moves.urllib.parse.urlparse(url)
        expected_query_params = six.moves.urllib.parse.parse_qsl(parsed.query)
        expected_url = '/'.join(item.strip('/') for item in urls if item)

        self.assertDictEqual(
            params,
            dict(expected_query_params)
        )

        self.assertTrue(url.startswith(expected_url))

    @data(
        {
            'course_id': 'course-v1:MITx+4.605x+3T2017',
            'expected_org': 'MITx'
        },
        {
            'course_id': 'WestonHS/PFLC1x/3T2015',
            'expected_org': 'WestonHS'
        },
        {
            'course_id': '',
            'expected_org': None
        },

    )
    @unpack
    def test_extract_course_org(self, course_id, expected_org):
        """
        Tests that utils.extract_course_org works as expected.
        """
        org = utils.extract_course_org(course_id)
        self.assertEqual(
            org,
            expected_org
        )

    def test_get_config_does_not_exist(self):
        """
        Tests that utils.get_config if file does not exist.
        """
        del os.environ['VIDEO_PIPELINE_CFG']

        with self.assertRaises(IOError):
            utils.get_config(yaml_config_file='does_not_exist')

    def test_get_config_with_default(self):
        """
        Tests that utils.get_config works as expected when reading default config.
        """
        del os.environ['VIDEO_PIPELINE_CFG']

        instance_config = utils.get_config()
        self.assertNotEqual(instance_config, {})

        # read the default config file
        default_yaml_config_file = os.path.join(
            utils.CONFIG_ROOT_DIR,
            utils.DEFAULT_CONFIG_FILE_NAME
        )
        with open(default_yaml_config_file, 'r') as config:
            config_dict = yaml.safe_load(config)

        # read the default static config file
        with open(utils.STATIC_CONFIG_FILE_PATH, 'r') as config:
            static_config_dict = yaml.safe_load(config)

        self.assertDictEqual(
            instance_config,
            dict(config_dict, **static_config_dict)
        )

    def test_get_config_with_path(self):
        """
        Tests that utils.get_config works as expected when reading config from environment path.
        """
        with patch('VEDA.utils.STATIC_CONFIG_FILE_PATH', self.static_file_path):
            instance_config = utils.get_config()
        self.assertDictEqual(instance_config, dict(TEST_CONFIG, **TEST_STATIC_CONFIG))

    @data(
        {
            'url': 'http://sandbox.edx.org/do?aaa=11&vvv=234',
            'params_to_scrub': ['aaa'],
            'expected_scrubbed_value': 'XX'
        },
        {
            'url': 'http://sandbox.edx.org/do?aaa=1&vvv=234',
            'params_to_scrub': ['aaa', 'vvv'],
            'expected_scrubbed_value': 'XXX'
        },
        {
            'url': 'http://sandbox.edx.org/do?aaa=1&vvv=234',
            'params_to_scrub': ['zzzz'],
            'expected_scrubbed_value': None
        },
    )
    @unpack
    def test_scrub_query_params(self, url, params_to_scrub, expected_scrubbed_value):
        """
        Tests that utils.scrub_query_params works as expected.
        """
        scrubed_url = utils.scrub_query_params(url, params_to_scrub)
        if expected_scrubbed_value:
            self.assertIn(expected_scrubbed_value, scrubed_url)


class DeleteDirectoryContentsTests(TestCase):
    """
    Tests for `delete_directory_contents` util function.
    """
    def setUp(self):
        """
        Tests setup.
        """
        # create a temp directory with temp directories and files in it
        self.temp_dir = tempfile.mkdtemp()
        dir_paths = ['{}/dir{}'.format(self.temp_dir, index) for index in range(5)]
        for dir_path in dir_paths:
            os.makedirs(dir_path)
            __, file_path = tempfile.mkstemp(
                suffix='.txt',
                dir=dir_path
            )
            with open(file_path, 'w') as outfile:
                outfile.write(str(TEST_CONFIG))

        # create a temp file in root temp directory
        with open('{}/{}'.format(self.temp_dir, 'temp_file.text'), 'w') as outfile:
            outfile.write(str(TEST_CONFIG))

    def tearDown(self):
        """
        Reverse the setup
        """
        shutil.rmtree(self.temp_dir)

    def test_delete_directory_contents(self):
        """
        Tests that utils.scrub_query_params works as expected.
        """
        # Verify that directory is not empty
        self.assertEqual(
            len(glob.glob('{path}/*'.format(path=self.temp_dir))),
            6
        )

        utils.delete_directory_contents(self.temp_dir)

        # Verify that directory is empty
        self.assertEqual(
            glob.glob('{path}/*'.format(path=self.temp_dir)),
            []
        )
