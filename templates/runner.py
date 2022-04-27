import argparse
import importlib.util
import io
import json
import os
import sys
import traceback
from contextlib import redirect_stdout
from enum import Enum


parser = argparse.ArgumentParser()
parser.add_argument('-u', help="User code")
parser.add_argument('-a', help="Author code")
parser.add_argument('-t', help="Test code")
parser.add_argument('-pre', help="User code")

parser.add_argument('--testlib', help="Test lib", default=None)
parser.add_argument('--default-testlib', help="Default Test lib")
parser.add_argument('--run-only', help="Skip checks", action='store_true')


class ExitCode(Enum):
    ok = 0
    tests_failed = 1
    user_code_failed = 2


class CheckerStream:
    def __init__(self):
        TEST_OUTPUT_FD = int(os.getenv('TEST_OUTPUT_FD'))
        self.stream = os.fdopen(TEST_OUTPUT_FD, 'w')

    def write(self, msg):
        self.stream.write(msg)


def format_traceback():
    """Makes appropriate for us traceback"""
    cl, error, tb = sys.exc_info()
    lines = [x for x in traceback.format_tb(tb)
             if 'File "runner.py"' in x]
    lines.insert(0, "Traceback (most recent call last):\n")
    lines += traceback.format_exception_only(cl, error)
    return "".join(lines)


def read_src(fname, delete=False):
    with open(fname, 'r+') as f:
        content = f.read()

        if delete:
            f.truncate(0)
    return content


def load_testlib(testlib_version, default_testlib):
    testlib_file_path = f'/testlibs/{testlib_version}.py'
    used_version = testlib_version

    if not os.path.exists(testlib_file_path):
        testlib_file_path = f'/testlibs/{default_testlib}.py'
        used_version = default_testlib

    spec = importlib.util.spec_from_file_location(
        'testlib',
        testlib_file_path,
    )
    testlib = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(testlib)

    return used_version, testlib


if __name__ == "__main__":

    args = vars(parser.parse_args())

    pre_code_file = args.get('pre', None)
    user_code = read_src(args.get('u', 'submission.py'), delete=True)
    run_only = args.get('run_only', False)
    checker_stream = CheckerStream()

    if not run_only:
        test_code = read_src(args.get('t', 'test_code.py'), delete=True)

        testlib_version = args.get("testlib")
        default_testlib_version = args.get("default_testlib")

        used_testlib_version, testlib = load_testlib(
            testlib_version=testlib_version,
            default_testlib=default_testlib_version,
        )

    try:
        if pre_code_file:
            pre_code = read_src(pre_code_file, delete=True)
            exec(pre_code)

        user_stream = io.StringIO()
        with redirect_stdout(user_stream):
            exec(user_code)
        user_output = user_stream.getvalue().strip()
        output = str(user_output)
        print(output)
    except (SystemExit):  # noqa E722
        checker_stream.write(json.dumps({'id': 'TrainerError.Error'}))
        exit(ExitCode.user_code_failed.value)
    except:  # noqa E722
        print(format_traceback(), file=sys.stderr)
        exit(ExitCode.user_code_failed.value)

    if not run_only:
        solved = True
        test_output = ""
        try:
            devnull = io.StringIO()
            with redirect_stdout(devnull):
                exec(test_code)
        except AssertionError as err:
            solved = False
            test_output = str(err.args[0]) if err.args else json.dumps({'id': 'TrainerError.Error'})
        except:  # noqa E722
            solved = False
            test_output = json.dumps({'id': "TrainerError.CodeIsNotCorrect"})

        checker_stream.write(test_output)
        if not solved:
            exit(ExitCode.tests_failed.value)
