"""
Check code quality
"""
from __future__ import absolute_import
from __future__ import print_function
import os
import re

from paver.easy import BuildFailure, cmdopts, sh, task

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPORTS_DIR = os.path.join(ROOT_DIR, 'reports')

PACKAGES = [
    'VEDA',
    'VEDA_OS01',
    'control',
    'frontend',
    'youtube_callback',
    'scripts',
    'bin',
    'pavelib',
]


@task
@cmdopts([
    ("limit=", "l", "limit for number of acceptable violations"),
])
def run_pep8(options):
    """
    Run pep8 on system code.
    Fail the task if any violations are found.
    """
    violations_limit = int(getattr(options, 'limit', -1))

    sh('pep8 . | tee {report_dir}/pep8.report'.format(report_dir=REPORTS_DIR))

    num_violations, __ = _count_pep8_violations(
        '{report_dir}/pep8.report'.format(report_dir=REPORTS_DIR)
    )

    violations_message = violation_message('pep8', violations_limit, num_violations)
    print(violations_message)

    # Fail if number of violations is greater than the limit
    if num_violations > violations_limit > -1:
        raise BuildFailure(violations_message)


def _count_pep8_violations(report_file):
    """
    Returns a tuple of (num_violations, violations_list) for all
    pep8 violations in the given report_file.
    """
    with open(report_file) as f:
        violations_list = f.readlines()

    num_lines = len(violations_list)
    return num_lines, violations_list


@task
@cmdopts([
    ('errors', 'e', 'Check for errors only'),
    ('limit=', 'l', 'limit for number of acceptable violations'),
])
def run_pylint(options):
    """
    Run pylint on system code. When violations limit is passed in,
    fail the task if too many violations are found.
    """
    num_violations = 0
    violations_limit = int(getattr(options, 'limit', -1))
    errors = getattr(options, 'errors', False)

    flags = []
    if errors:
        flags.append('--errors-only')

    sh(
        'PYTHONPATH={python_path} pylint {packages} {flags} --msg-template={msg_template} | '
        'tee {report_dir}/pylint.report'.format(
            python_path=ROOT_DIR,
            packages=' '.join(PACKAGES),
            flags=' '.join(flags),
            msg_template='"{path}:{line}: [{msg_id}({symbol}), {obj}] {msg}"',
            report_dir=REPORTS_DIR
        )
    )

    num_violations = _count_pylint_violations(
        '{report_dir}/pylint.report'.format(report_dir=REPORTS_DIR)
    )
    violations_message = violation_message('pylint', violations_limit, num_violations)
    print(violations_message)

    # Fail if number of violations is greater than the limit
    if num_violations > violations_limit > -1:
        raise BuildFailure(violations_message)


def _count_pylint_violations(report_file):
    """
    Parses a pylint report line-by-line and determines the number of violations reported
    """
    num_violations_report = 0
    # An example string:
    # scripts/reencode_crawler.py:57: [C0303(trailing-whitespace), ] Trailing whitespace
    pylint_pattern = re.compile(r'.(\d+):\ \[(\D\d+.+\]).')

    for line in open(report_file):
        violation_list_for_line = pylint_pattern.split(line)
        # If the string is parsed into four parts, then we've found a violation. Example of split parts:
        # test file, line number, violation name, violation details
        if len(violation_list_for_line) == 4:
            num_violations_report += 1

    return num_violations_report


def violation_message(task_name, violations_limit, num_violations):
    """
    Returns violation message for a task.

    Arguments:
        task_name (str): name of task
        violations_limit (int): total number of violations allowed
        num_violations (int): violations occurred
    """
    return '{violations_base_message}{violations_limit_message}'.format(
        violations_base_message='Too many {} violations. Number of {} violations: {}. '.format(
            task_name, task_name, num_violations
        ),
        violations_limit_message='The limit is {violations_limit}.'.format(violations_limit=violations_limit),
    )
