# File : shell.py
# Author : Sébastien Deriaz
# License : GPL

from typing import ParamSpec, TypeVar

P = ParamSpec("P")
R = TypeVar("R")

# @dataclass(frozen=True)
# class ShellCommandInfo:
#     name: str
#     aliases: tuple[str, ...] = ()
#     help: str = ""

# def shell_command(
#     help: str,
#     *,
#     name: str | None = None,
#     aliases: tuple[str, ...] = (),
# ) -> Callable[[Callable[P, R]], Callable[P, R]]:
#     def decorator(func: Callable[P, R]) -> Callable[P, R]:
#         cmd_name = name or func.__name__
#         func.__shell_command__ = ShellCommandInfo(name=cmd_name, aliases=aliases, help=help)
#         return func
#     return decorator
