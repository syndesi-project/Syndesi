# File : asyncify.py
# Author : Sébastien Deriaz
# License : GPL
"""
Marker decorator consumed by scripts/gen_async.py.

@asyncify on a method means "scripts/gen_async.py generates this method's
async twin" (see that script's module docstring for the exact rewrite
rules it applies). The decorator itself is a no-op at runtime - it
returns the function completely unchanged. It exists purely so the
generator script can recognize, via ast.FunctionDef.decorator_list,
which methods to process - nothing dynamic happens because of it.
"""

from collections.abc import Callable
from typing import TypeVar

_F = TypeVar("_F", bound=Callable)


def asyncify(func: _F) -> _F:
    """Mark a method for async-twin generation by scripts/gen_async.py."""
    return func
