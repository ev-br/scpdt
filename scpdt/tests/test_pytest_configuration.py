import pytest
from pathlib import PosixPath


from . import module_cases, failure_cases, failure_cases_2, stopwords_cases

pytest_plugins = ['pytester']

"""
Test that pytest uses the DTChecker for doctests
"""
def test_module_cases(pytester):
    path_str = module_cases.__file__
    python_file = PosixPath(path_str)
    result = pytester.inline_run(python_file, "--doctest-scpdt")
    assert result.ret == pytest.ExitCode.OK


def test_failure_cases(pytester):
    file_list = [failure_cases, failure_cases_2]
    for file in file_list:
        path_str = file.__file__
        python_file = PosixPath(path_str)
        result = pytester.inline_run(python_file, "--doctest-scpdt")
    assert result.ret == pytest.ExitCode.TESTS_FAILED
    

"""
Test that pytest uses the DTParser for doctests
"""
def test_stopword_cases(pytester):
    path_str = stopwords_cases.__file__
    python_file = PosixPath(path_str)
    result = pytester.inline_run(python_file, "--doctest-scpdt")
    assert result.ret == pytest.ExitCode.OK
