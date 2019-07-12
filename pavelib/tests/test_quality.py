"""
Tests for paver quality tasks
"""
from __future__ import absolute_import
import os
import tempfile
import unittest

import paver.tasks
from ddt import data, ddt, file_data, unpack
from mock import Mock, patch
from paver.easy import call_task

import pavelib.quality


@ddt
class TestPaverQualityViolations(unittest.TestCase):
    """
    For testing the paver violations-counting tasks
    """
    def setUp(self):
        super(TestPaverQualityViolations, self).setUp()
        self.f = tempfile.NamedTemporaryFile(delete=False)
        self.f.close()
        self.addCleanup(os.remove, self.f.name)

    def test_pylint_parser_checks_formatting(self):
        """
        Tests that only correctly formatted lines are considered as violations.
        """
        with open(self.f.name, 'w') as f:
            f.write("hello")
        num = pavelib.quality._count_pylint_violations(f.name)  # pylint: disable=protected-access
        self.assertEqual(num, 0)

    @file_data('pylint_test_list.json')
    def test_pylint_parser_count_violations(self, value):
        """
        Tests that pylint parser works as exepcted.

        Tests:
        - Different types of violations
        - One violation covering multiple lines
        """
        with open(self.f.name, 'w') as f:
            f.write(value)
        num = pavelib.quality._count_pylint_violations(f.name)  # pylint: disable=protected-access
        self.assertEqual(num, 1)

    def test_pep8_parser(self):
        """
        Tests that pep8 parser works as expected.
        """
        with open(self.f.name, 'w') as f:
            f.write("hello\nhithere")
        num, __ = pavelib.quality._count_pep8_violations(f.name)  # pylint: disable=protected-access
        self.assertEqual(num, 2)


@ddt
class TestPaverQuality(unittest.TestCase):
    """
    For testing the paver quality tasks
    """

    def setUp(self):
        super(TestPaverQuality, self).setUp()
        # this is required so that each test will clean environment
        paver.tasks.environment = paver.tasks.Environment()

        self.test_code_dir = os.path.join(os.path.dirname(__file__), 'pavelib_test_code')

        # Mock _count_pep8_violations to return a violation
        self._mock_count_pep8_violations = Mock(
            return_value=(1, ['abc/envs/common.py:32:2: E225 missing whitespace around operator'])
        )

        # Mock _count_pylint_violations to return a violation
        self._mock_count_pylint_violations = Mock(return_value=1)

    @staticmethod
    def assert_pylint_sh_call(mock_quality_sh):
        """
        Assert that correct pylint sh call is executed
        """
        mock_quality_sh.assert_called_once_with(
            'PYTHONPATH={python_path} pylint {packages} {flags} --msg-template={msg_template} | '
            'tee {report_dir}/pylint.report'.format(
                python_path=pavelib.quality.ROOT_DIR,
                packages=' '.join(pavelib.quality.PACKAGES),
                flags=' '.join([]),
                msg_template='"{path}:{line}: [{msg_id}({symbol}), {obj}] {msg}"',
                report_dir=pavelib.quality.REPORTS_DIR
            )
        )

    @data(
        {
            'options': {}
        },
        {
            'options': {'limit': 1}
        },
        {
            'options': {'limit': 2}
        }
    )
    @unpack
    @patch('pavelib.quality.sh')
    @patch('pavelib.quality.violation_message')
    def test_run_pep8_success(self, mock_violation_message, mock_quality_sh, options):
        """
        Tests that run_pep8 task works as expected when violations does not exceed the limit.
        """
        with patch('pavelib.quality._count_pep8_violations', self._mock_count_pep8_violations):
            call_task('pavelib.quality.run_pep8', options=options)

            limit = options.get('limit', -1)
            mock_violation_message.assert_called_once_with('pep8', limit, 1)
            mock_quality_sh.assert_called_once_with(
                'pep8 . | tee {report_dir}/pep8.report'.format(report_dir=pavelib.quality.REPORTS_DIR)
            )

    @patch('pavelib.quality.sh')
    @patch('pavelib.quality.violation_message')
    def test_run_pep8_failure(self, mock_violation_message, mock_quality_sh):
        """
        Tests that run_pep8 task works as expected when violations exceed the limit.
        """
        with patch('pavelib.quality._count_pep8_violations', self._mock_count_pep8_violations):
            with self.assertRaises(SystemExit):
                call_task('pavelib.quality.run_pep8', options={'limit': 0})

            mock_violation_message.assert_called_once_with('pep8', 0, 1)
            mock_quality_sh.assert_called_once_with(
                'pep8 . | tee {report_dir}/pep8.report'.format(report_dir=pavelib.quality.REPORTS_DIR)
            )

    @data(
        {
            'options': {}
        },
        {
            'options': {'limit': 1}
        },
        {
            'options': {'limit': 2}
        }
    )
    @unpack
    @patch('pavelib.quality.sh')
    @patch('pavelib.quality.violation_message')
    def test_pylint_success(self, mock_violation_message, mock_quality_sh, options):
        """
        Tests that run_pylint task works as expected when violations does not exceed the limit.
        """
        with patch('pavelib.quality._count_pylint_violations', self._mock_count_pylint_violations):
            call_task('pavelib.quality.run_pylint', options=options)

            limit = options.get('limit', -1)
            mock_violation_message.assert_called_once_with('pylint', limit, 1)
            self.assert_pylint_sh_call(mock_quality_sh)

    @patch('pavelib.quality.sh')
    @patch('pavelib.quality.violation_message')
    def test_pylint_failure(self, mock_violation_message, mock_quality_sh):
        """
        Tests that run_pylint task works as expected when violations exceed the limit.
        """
        with patch('pavelib.quality._count_pylint_violations', self._mock_count_pylint_violations):
            with self.assertRaises(SystemExit):
                call_task('pavelib.quality.run_pylint', options={'limit': 0})

            mock_violation_message.assert_called_once_with('pylint', 0, 1)
            self.assert_pylint_sh_call(mock_quality_sh)

    @patch('pavelib.quality.violation_message')
    def test_pylint_with_test_code(self, mock_violation_message):
        """
        Tests that run_pylint task works as expected for actual python code.
        """
        with patch('pavelib.quality.PACKAGES', [self.test_code_dir]):
            call_task('pavelib.quality.run_pylint', options={'limit': 3})

        mock_violation_message.assert_called_once_with('pylint', 3, 3)

    @patch('pavelib.quality.violation_message')
    def test_pylint_with_errors_only(self, mock_violation_message):
        """
        Tests that run_pylint task works as expected with `errors` option.
        """
        with patch('pavelib.quality.PACKAGES', [self.test_code_dir]):
            call_task('pavelib.quality.run_pylint', options={'errors': True, 'limit': 1})

        mock_violation_message.assert_called_once_with('pylint', 1, 1)

    @data(
        {
            'task_name': 'pep8', 'violations_limit': 3, 'num_violations': 2
        },
        {
            'task_name': 'pyilnt', 'violations_limit': 1, 'num_violations': 2
        },
    )
    def test_violation_message(self, kwargs):
        """
        Tests that violation_message function works as expected.
        """
        message = pavelib.quality.violation_message(**kwargs)
        self.assertEqual(
            message,
            'Too many {} violations. Number of {} violations: {}. The limit is {}.'.format(
                kwargs['task_name'],
                kwargs['task_name'],
                kwargs['num_violations'],
                kwargs['violations_limit'],
            )
        )
