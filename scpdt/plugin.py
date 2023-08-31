"""
A pytest plugin that provides enhanced doctesting for Pydata libraries
"""
import bdb
import inspect
import os
import shutil
import numpy as np
import pytest

from _pytest import doctest, outcomes
from _pytest.doctest import DoctestModule, DoctestTextfile
from _pytest.pathlib import import_path
from _pytest.outcomes import skip, OutcomeException

from scpdt.impl import DTChecker, DTParser, DTFinder, DebugDTRunner
from scpdt.conftest import dt_config
from .util import np_errstate, matplotlib_make_nongui

pytest_version = pytest.__version__


copied_files = []
modules = []

def pytest_configure(config):
    """
    Allow plugins and conftest files to perform initial configuration.
    """

    doctest._get_runner = _get_runner
    doctest._get_checker = _get_checker
    doctest.DoctestModule = DTModule
    doctest.DoctestTextfile = DTTextfile

def pytest_unconfigure(config):
    """
    Called before test process is exited.
    """

    # Delete all local files copied to the current working directory
    if copied_files:
        try:
            for filepath in copied_files:
                os.remove(filepath)
        except FileNotFoundError:
            pass


"""
These helper functions are used to handle file paths and extensions of different pytest versions
"""
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
    This hook ensures Cython files (.pyx) are collected by pytest
    """
    if _suffix(file_path) == ".pyx":
        return DTModule.from_parent(parent, path=file_path)


def _get_checker():
    """
    Override function to return an instance of DTChecker
    """
    return DTChecker(config=dt_config)


def copy_local_files(local_resources, destination_dir):
    """
    Copy necessary local files for doctests to the current working directory. 
    The files to be copied are defined by the `local_resources` attribute of a DTConfig instance.
    """
    for value in local_resources.values():
        for filepath in value:
            basename = os.path.basename(filepath)
            dest_path = os.path.join(destination_dir, basename)

            if not os.path.exists(dest_path):
                shutil.copy(filepath, destination_dir)
                copied_files.append(dest_path)    
    return copied_files


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

        # if local files are specified by the `local_resources` attribute, copy them to the current working directory
        if dt_config.local_resources:
            copy_local_files(dt_config.local_resources, os.getcwd())

        # The `_pytest.doctest` module uses the internal doctest parsing mechanism.
        # We plugin scpdt's `DTFinder` that uses the `DTParser` which parses the doctest examples 
        # from the python module or file and filters out stopwords and pseudocode.
        finder = DTFinder(config=dt_config)
        optionflags = doctest.get_optionflags(self)

        # We plug in `PytestDTRunner`
        runner = _get_runner(
            verbose=False,
            optionflags=optionflags,
            checker=_get_checker()
        )

        
        def collect_and_yield_tests(module, finder, runner, method=None):
            if inspect.ismodule(module):
                for test in finder.find(method or module, module=module):
                    if test.examples: # skip empty doctests
                        generate_log(module, test)
                        yield doctest.DoctestItem.from_parent(
                            self, name=test.name, runner=runner, dtest=test
                        )
            else:
                for entry in dir(module):
                    if inspect.ismodule(entry):
                        for test in finder.find(method or entry, module=entry):
                            if test.examples: # skip empty doctests
                                generate_log(entry, test)
                                yield doctest.DoctestItem.from_parent(
                                    self, name=test.name, runner=runner, dtest=test
                                )
                

        for method in module.__dict__.values():
            if _is_numpy_ufunc(method):
                yield from collect_and_yield_tests(module, finder, runner, method)
        yield from collect_and_yield_tests(module, finder, runner)


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

        # if local files are specified by the `local_resources` attribute, copy them to the current working directory
        if dt_config.local_resources:
            copy_local_files(dt_config.local_resources, os.getcwd())

        # We plug in `PytestDTRunner`
        runner = _get_runner(
            verbose=False,
            optionflags=optionflags,
            checker=_get_checker()
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
    Return instance of DTParser
    Please refer to `testmod` source for a discussion of the order of context managers.
    """
    return DTParser(config=dt_config)


def _get_runner(checker, verbose, optionflags):
    import doctest
    """
    Override function to return instance of PytestDTRunner
    """
    class PytestDTRunner(DebugDTRunner):
        def run(self, test, compileflags=None, out=None, clear_globs=False):
            """
            Run tests in context managers.
            Restore the errstate/print state after each docstring.
            Also make MPL backend non-GUI and close the figures.
            The order of context managers is actually relevant. Consider
            user_context_mgr that turns warnings into errors.
            Additionally, suppose that MPL deprecates something and plt.something
            starts issuing warngings. Now all of those become errors
            *unless* the `mpl()` context mgr has a chance to filter them out
            *before* they become errors in `config.user_context_mgr()`.
            """
            with np_errstate():
                with dt_config.user_context_mgr(test):
                    with matplotlib_make_nongui():
                        super().run(test, compileflags=compileflags, out=out, clear_globs=clear_globs)

        """
        Almost verbatim copy of `_pytest.doctest.PytestDoctestRunner` except we utilize
        DTConfig's `nameerror_after_exception` attribute in place of doctest's `continue_on_failure`.
        """
        def report_failure(self, out, test, example, got):
            failure = doctest.DocTestFailure(test, example, got)
            if dt_config.nameerror_after_exception:
                out.append(failure)
            else:
                raise failure

        def report_unexpected_exception(self, out, test, example, exc_info):
            if isinstance(exc_info[1], OutcomeException):
                raise exc_info[1]
            if isinstance(exc_info[1], bdb.BdbQuit):
                outcomes.exit("Quitting debugger")
            failure = doctest.UnexpectedException(test, example, exc_info)
            if dt_config.nameerror_after_exception:
                out.append(failure)
            else:
                raise failure
            
    return PytestDTRunner(checker=checker, verbose=verbose, optionflags=optionflags, config=dt_config)


def generate_log(module, test):
    if test.examples:
        with open('doctest.log', 'a') as LOGFILE:
            if module.__name__ not in modules:
                LOGFILE.write("\n" + module.__name__ + "\n")
                LOGFILE.write("="*len(module.__name__) + "\n")
                modules.append(module.__name__)
            LOGFILE.write(test.name + "\n")


def _is_numpy_ufunc(method):
    while True:
        try:
            method = method.__wrapped__
        except AttributeError:
            break
    return isinstance(method, np.ufunc)
