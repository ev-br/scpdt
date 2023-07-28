"""
A pytest plugin that provides enhanced doctesting for Pydata libraries
"""


import pytest
from _pytest import doctest
from _pytest.doctest import DoctestModule, DoctestTextfile
from _pytest.pathlib import import_path
from _pytest.outcomes import skip
from pathlib import Path


from scpdt.impl import DTChecker, DTConfig, DTParser, DTFinder

pytest_version = pytest.__version__

def pytest_addoption(parser):
    """
    Register argparse-style options and ini-style config values,
    called once at the beginning of a test run.
    """
    parser.addoption(
        "--doctest-scpdt",
        action="store_true",
        default=False,
        help="Run doctests in all .py modules using the scpdt tool",
        dest="doctestscpdt"
    )
    parser.addoption(
        "--doctest-only", 
        action="store_true",
        help="Perform doctests only using the scpdt tool."
        )
    parser.addini(
        "doctest_optionflags",
        "Option flags for doctests",
        type="args",
        default=["NORMALIZE_WHITESPACE", "ELLIPSIS", "IGNORE_EXCEPTION_DETAIL"]
        )
    parser.addini(
        "doctest_scpdt",
        help="Enable running doctests using the scpdt tool",
        default=False
    )


def pytest_configure(config):
    """
    Allow plugins and conftest files to perform initial configuration.
    """
    if not any((config.option.doctestscpdt, config.getini("doctest_scpdt"))):
        return

    doctest._get_checker = _get_checker
    doctest.DoctestModule = DTModule
    doctest.DoctestTextfile = DTTextfile


if pytest_version < '7.0':
    def _filepath(path):
        return path.basename
    def _suffix(path):
        return path.ext
else:
    def _filepath(path):
        return path.name
    def _suffix(path):
        return path.suffix


def pytest_collect_file(file_path, parent):
    """
    This hook looks for Python files (.py) and text files with doctests (.rst, for example)
    """
    config = parent.config
    # This code is copy-pasted from the `_pytest.doctest` module(pytest 7.4.0):
    # https://github.com/pytest-dev/pytest/blob/7c30f674c58ee16f2b74ef85bb8765252764ef70/src/_pytest/doctest.py#L125
    # However, helper functions: `_suffix` and `_filepath` are used to handle paths and extensions depending on the pytest versions
    if _suffix(file_path) == ".py":
        if config.getoption("doctestscpdt") and not any(
            (_is_setup_py(file_path), _is_main_py(file_path))
        ):
            return DTModule.from_parent(parent, path=file_path)
    elif _is_doctest(config, file_path, parent):
        return DTTextfile.from_parent(parent, path=file_path)
    return None


def _is_setup_py(path):
    if _filepath(path) != "setup.py":
        return False
    contents = path.read_bytes()
    return b"setuptools" in contents or b"distutils" in contents


def _is_doctest(config, path, parent):
    if _suffix(path) in (".txt", ".rst") and parent.session.isinitpath(path):
        return True
    globs = config.getoption("doctestglob")
    return any(doctest.fnmatch_ex(glob, path) for glob in globs)


def _is_main_py(path):
    return _filepath(path) == "__main__.py"


def _get_checker():
    """
    Override function to return an instance of DTChecker with default configurations
    """
    return DTChecker(config=DTConfig())


class DTModule(DoctestModule):
    """
    This class extends the DoctestModule class provided by pytest. 
    The purpose of DTModule is to override the behavior of the collect method, 
    which is called by pytest to collect and generate test items for doctests in the 
    specified module or file.
    """
    def collect(self):
        # This code is copy-pasted from the `_pytest.doctest` module(pytest 7.4.0):
        # https://github.com/pytest-dev/pytest/blob/448563caaac559b8a3195edc58e8806aca8d2c71/src/_pytest/doctest.py#L497
        if self.path.name == "setup.py":
            return
        if self.path.name == "conftest.py":
            module = self.config.pluginmanager._importconftest(
                self.path,
                self.config.getoption("importmode"),
                rootpath=self.config.rootpath
            )
        else:
            try:
                module = import_path(
                    self.path,
                    root=self.config.rootpath,
                    mode=self.config.getoption("importmode"),
                )
            except ImportError:
                if self.config.getvalue("doctest_ignore_import_errors"):
                    skip("unable to import module %r" % self.path)
                else:
                    raise

        # The `_pytest.doctest` module uses the internal doctest parsing mechanism.
        # We plugin scpdt's `DTFinder` that uses the `DTParser` which parses the doctest examples 
        # from the python module or file and filters out stopwords and pseudocode.
        finder = DTFinder(config=DTConfig())

        # the rest remains unchanged
        optionflags = doctest.get_optionflags(self)
        runner = doctest._get_runner(
            verbose=False,
            optionflags=optionflags,
            checker=_get_checker(),
            continue_on_failure=doctest._get_continue_on_failure(self.config),
        )

        for test in finder.find(module, module.__name__):
            if test.examples:  # skip empty doctests
                yield doctest.DoctestItem.from_parent(
                    self, name=test.name, runner=runner, dtest=test
                )


class DTTextfile(DoctestTextfile):
    """
    This class extends the DoctestTextfile class provided by pytest. 
    The purpose of DTTextfile is to override the behavior of the collect method, 
    which is called by pytest to collect and generate test items for doctests in 
    the specified text files.
    """
    def collect(self):
        # This code is copy-pasted from `_pytest.doctest` module(pytest 7.4.0):
        # https://github.com/pytest-dev/pytest/blob/448563caaac559b8a3195edc58e8806aca8d2c71/src/_pytest/doctest.py#L417
        encoding = self.config.getini("doctest_encoding")
        text = self.path.read_text(encoding)
        filename = str(self.path)
        name = self.path.name
        globs = {"__name__": "__main__"}

        optionflags = doctest.get_optionflags(self)

        runner = doctest._get_runner(
            verbose=False,
            optionflags=optionflags,
            checker=_get_checker(),
            continue_on_failure=doctest._get_continue_on_failure(self.config)
        )

        # We plug in an instance of `DTParser` which parses the doctest examples from the text file and
        # filters out stopwords and pseudocode.
        parser = _get_parser()

        # the rest remains unchanged
        test = parser.get_doctest(text, globs, name, filename, 0)
        if test.examples:
            yield doctest.DoctestItem.from_parent(
                self, name=test.name, runner=runner, dtest=test
            )


def _get_parser():
    """
    Return instance of DTParser with default configuration
    """
    return DTParser(config=DTConfig())

