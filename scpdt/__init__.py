"""
Doctests on steroids.

Whitespace-insensitive, numpy-aware, floating-point-aware doctest helpers.
"""


__version__ = "0.1"

from ._impl import DTChecker, DTFinder, DTParser, DTRunner, DebugDTRunner, DTConfig
from ._frontend import testmod, testfile, find_doctests, run_docstring_examples

