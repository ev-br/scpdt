"""
Configurable, whitespace-insensitive, floating-point-aware doctest helpers.

PYTEST_DONT_REWRITE
"""


__version__ = "1.4dev0"

"""
try:
    # register internal modules with pytest; obscure errors galore otherwise
    import pytest
    pytest.register_assert_rewrite(
        "scipy_doctest",
        "scipy_doctest.conftest", "scipy_doctest.impl", "scipy_doctest.util",
        "scipy_doctest.frontend", "scipy_doctest.plugin"
    )
except ModuleNotFoundError:
    # pytest is optional, so nothing to do
    pass
"""

from .impl import DTChecker, DTFinder, DTParser, DTRunner, DebugDTRunner, DTConfig  # noqa
from .frontend import testmod, testfile, find_doctests, run_docstring_examples      # noqa

