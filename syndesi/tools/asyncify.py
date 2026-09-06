# File : asyncify.py
# Author : Sébastien Deriaz
# License : GPL
"""
Marker decorators consumed by scripts/gen_async.py and scripts/gen_sync.py.

@asyncify on a sync method means "scripts/gen_async.py generates this
method's async twin" (see that script's module docstring for the exact
rewrite rules it applies).

@no_sync on an async method (on a class named AsyncXxx) means
"scripts/gen_sync.py must NOT generate a blocking twin for this method" -
used for methods with no meaningful sync equivalent (e.g. ones built on
asyncio.gather/TaskGroup). The generated sync class still gets a same-named
method, but its body just raises NotImplementedError.

Both decorators are no-ops at runtime - they return the function completely
unchanged. They exist purely so the generator scripts can recognize, via
ast.FunctionDef.decorator_list, which methods to process - nothing dynamic
happens because of them.
"""

from collections.abc import Callable
from typing import TypeVar

_F = TypeVar("_F", bound=Callable)


def asyncify(func: _F) -> _F:
    """Mark a sync method for async-twin generation by scripts/gen_async.py."""
    return func


def no_sync(func: _F) -> _F:
    """Exclude an async method from sync-twin generation by scripts/gen_sync.py."""
    return func
