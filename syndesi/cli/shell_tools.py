# File : shell_tools.py
# Author : Sébastien Deriaz
# License : GPL


# @dataclass
# class CommandSpec:
#     name: str
#     func: Callable[..., Any]  # the underlying function object
#     help: str = ""
#     aliases: tuple[str, ...] = ()
#     hidden: bool = False
#     dangerous: bool = False
#     owner_cls: type | None = None  # populated when collected
#     method_kind: str = "function"  # "instance" | "class" | "static" | "function"


# # ---- Module-level registry (optional)
# # If you like auto-discovery, classes decorated with @collect_cli_exports
# # get added here at import time.
# CLI_CLASS_REGISTRY: set[type] = set()


# def iter_all_cli_specs(classes: Iterable[type]) -> Iterable[CommandSpec]:
#     """Yield CommandSpec for the given classes (or CLI_CLASS_REGISTRY if you pass that)."""
#     for cls in classes:
#         for spec in getattr(cls, "__cli_exports__", ()):
#             yield from spec


# # ---- Decorators
# def cli_command(
#     name: str | None = None,
#     *,
#     help: str = "",
#     aliases: tuple[str, ...] = (),
#     hidden: bool = False,
#     dangerous: bool = False,
# ) -> None:
#     """
#     Decorate any callable (method or function) to mark it as CLI-visible.
#     Attach a CommandSpec to the function object. Class binding is assigned later.
#     """

#     def deco(fn: Callable[..., Any]) -> None:
#         # Note: we attach spec on the underlying function (works for instance funcs).
#         spec = CommandSpec(
#             name=(name or fn.__name__).replace("_", "-"),
#             func=fn,
#             help=help or (fn.__doc__ or "").strip(),
#             aliases=aliases,
#             hidden=hidden,
#             dangerous=dangerous,
#         )
#         fn.__cli_export__ = spec
#         return fn

#     return deco


# def collect_cli_exports(cls: type) -> None:
#     """
#     Class decorator: scan the class for decorated methods (instance, classmethod, staticmethod),
#     create a stable list of CommandSpec, and attach it as __cli_exports__.
#     Also registers the class in CLI_CLASS_REGISTRY for optional auto-discovery.
#     """
#     exports: list[CommandSpec] = []

#     for _, obj in cls.__dict__.items():
#         # instance method (function descriptor)
#         if inspect.isfunction(obj):
#             spec: CommandSpec | None = getattr(obj, "__cli_export__", None)
#             if spec:
#                 spec.owner_cls = cls
#                 spec.method_kind = "instance"
#                 exports.append(spec)
#             continue

#         # classmethod / staticmethod wrap the underlying function in .__func__
#         if isinstance(obj, classmethod):
#             fn = obj.__func__
#             spec = getattr(fn, "__cli_export__", None)
#             if spec:
#                 spec.owner_cls = cls
#                 spec.method_kind = "class"
#                 exports.append(spec)
#             continue

#         if isinstance(obj, staticmethod):
#             fn = obj.__func__
#             spec = getattr(fn, "__cli_export__", None)
#             if spec:
#                 spec.owner_cls = cls
#                 spec.method_kind = "static"
#                 exports.append(spec)
#             continue

#     cls.__cli_exports__ = tuple(exports)
#     CLI_CLASS_REGISTRY.add(cls)
#     return cls
