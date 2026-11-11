# File : introspection.py
# Author : Sébastien Deriaz
# License : GPL
"""
What the GUI knows about a component, read from its code only

Nothing here is specific to the GUI and nothing has to be declared by the author of an
adapter, a protocol or a driver : the type hints of the constructor say what a component
is built on (its slots) and what it can be configured with (its fields), the numpy
docstring gives the help texts and the choices ({'TCP', 'UDP'}), and the public methods
are the commands of the test screen

    class SCPI(Protocol[SCPIBackend, bytes, str]):     -> PROTOCOL, provides str
        def __init__(self, adapter: Adapter[Any, bytes],   -> slot, accepts bytes adapters
                     termination: str | bytes = "\\n"):    -> field
"""

from __future__ import annotations

import enum
import inspect
import re
import sys
import types
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from functools import cache
from typing import Any, Literal, TypeVar, Union, get_args, get_origin, get_type_hints

from ...adapters.adapter import Adapter, AdapterCommon, AsyncAdapter
from ...adapters.stop_conditions import StopCondition
from ...drivers.driver import Driver, SubDriver
from ...protocols.protocol import AsyncProtocol, Protocol, ProtocolCommon
from ...tools.others import DEFAULT

# ┌───────┐
# │ Kinds │
# └───────┘


class Kind(StrEnum):
    """Layer a component belongs to"""

    ADAPTER = "Adapter"
    PROTOCOL = "Protocol"
    DRIVER = "Driver"
    SUBDRIVER = "SubDriver"

    @property
    def letter(self) -> str:
        """Abbreviation used in the event table, like the previous UI"""
        return {
            Kind.ADAPTER: "A",
            Kind.PROTOCOL: "P",
            Kind.DRIVER: "D",
            Kind.SUBDRIVER: "D",
        }[self]


COMPONENT_BASES: tuple[type, ...] = (
    Adapter,
    AsyncAdapter,
    Protocol,
    AsyncProtocol,
    SubDriver,
)

# Classes of the library itself : the methods they define are the plumbing every
# component shares, not what a given component is about
FRAMEWORK_BASES: tuple[type, ...] = (
    Adapter,
    AsyncAdapter,
    AdapterCommon,
    Protocol,
    AsyncProtocol,
    ProtocolCommon,
    Driver,
    SubDriver,
)


def kind_of(cls: type) -> Kind | None:
    """Kind of a component class, None if it isn't one"""
    if not isinstance(cls, type):
        return None
    if issubclass(cls, (Adapter, AsyncAdapter)):
        return Kind.ADAPTER
    if issubclass(cls, (Protocol, AsyncProtocol)):
        return Kind.PROTOCOL
    if issubclass(cls, Driver):
        return Kind.DRIVER
    if issubclass(cls, SubDriver):
        return Kind.SUBDRIVER
    return None


def is_component(obj: Any) -> bool:
    """True if obj is an adapter, a protocol or a (sub)driver instance"""
    return isinstance(obj, COMPONENT_BASES)


def is_async(cls: type) -> bool:
    """True for the async facades (AsyncIP, AsyncDelimited, ...)"""
    return issubclass(cls, (AsyncAdapter, AsyncProtocol))


# ┌──────────────┐
# │ Type algebra │
# └──────────────┘


def _union_members(hint: Any) -> list[Any] | None:
    if get_origin(hint) in (Union, types.UnionType):
        return list(get_args(hint))
    return None


def _substitute(arg: Any, mapping: dict[Any, Any]) -> Any:
    if isinstance(arg, TypeVar):
        return mapping.get(arg, arg)
    return arg


def generic_args(cls: type, target: type) -> tuple[Any, ...] | None:
    """
    Type arguments cls gives to the generic class target, following the bases

    >>> generic_args(IP, Adapter)
    (IPDescriptor, bytes)
    >>> generic_args(SCPI, Protocol)
    (SCPIBackend, bytes, str)

    TypeVars are returned for the parameters cls leaves open, None if cls doesn't
    derive from target
    """
    if cls is target:
        return tuple(getattr(target, "__parameters__", ()))
    for base in getattr(cls, "__orig_bases__", cls.__bases__):
        origin = get_origin(base) or base
        if not isinstance(origin, type) or origin is cls:
            continue
        try:
            if not issubclass(origin, target):
                continue
        except TypeError:
            continue
        result = generic_args(origin, target)
        if result is None:
            continue
        if get_origin(base) is not None:
            mapping = dict(zip(getattr(origin, "__parameters__", ()), get_args(base), strict=False))
            result = tuple(_substitute(arg, mapping) for arg in result)
        return result
    return None


def _type_arg_matches(expected: Any, actual: Any) -> bool:
    if expected is Any or isinstance(expected, TypeVar):
        return True
    # A parameter the candidate leaves open could be anything : don't refuse it
    if actual is Any or isinstance(actual, TypeVar):
        return True
    members = _union_members(expected)
    if members is not None:
        return any(_type_arg_matches(m, actual) for m in members)
    actual_members = _union_members(actual)
    if actual_members is not None:
        return all(_type_arg_matches(expected, m) for m in actual_members)
    expected_origin = get_origin(expected) or expected
    actual_origin = get_origin(actual) or actual
    if isinstance(expected_origin, type) and isinstance(actual_origin, type):
        return issubclass(actual_origin, expected_origin)
    return bool(expected == actual)


def accepts(hint: Any, cls: type) -> bool:
    """
    True if an instance of cls can be passed where hint is expected

    Only what can be decided from the classes is checked : Adapter[Any, bytes] accepts
    IP (an Adapter[IPDescriptor, bytes]) and refuses IPServer (an Adapter[..., IP])
    """
    members = _union_members(hint)
    if members is not None:
        return any(accepts(m, cls) for m in members)
    if hint is Any:
        return True
    if isinstance(hint, TypeVar):
        bound = hint.__bound__
        return True if bound is None else accepts(bound, cls)
    origin = get_origin(hint)
    if origin is None:
        return isinstance(hint, type) and issubclass(cls, hint)
    if not isinstance(origin, type) or not issubclass(cls, origin):
        return False
    actual = generic_args(cls, origin)
    if actual is None:
        return True
    return all(_type_arg_matches(e, a) for e, a in zip(get_args(hint), actual, strict=False))


def _mentions_component(hint: Any) -> bool:
    members = _union_members(hint)
    if members is not None:
        return any(_mentions_component(m) for m in members)
    if isinstance(hint, TypeVar):
        return hint.__bound__ is not None and _mentions_component(hint.__bound__)
    origin = get_origin(hint) or hint
    return isinstance(origin, type) and issubclass(origin, COMPONENT_BASES)


def type_name(hint: Any) -> str:
    """Short, readable form of a type hint : Adapter[Any, bytes], str | bytes, ..."""
    if hint is inspect.Parameter.empty or hint is None:
        return ""
    if hint is types.NoneType:
        return "None"
    if hint is Any:
        return "Any"
    members = _union_members(hint)
    if members is not None:
        return " | ".join(type_name(m) for m in members)
    if isinstance(hint, TypeVar):
        return hint.__name__
    origin = get_origin(hint)
    if origin is Literal:
        args = get_args(hint)
        if args == (DEFAULT,):
            return "DEFAULT"
        return "Literal[" + ", ".join(repr(a) for a in args) + "]"
    if origin is not None:
        args = get_args(hint)
        name = getattr(origin, "__name__", str(origin))
        return f"{name}[{', '.join(type_name(a) for a in args)}]" if args else name
    if isinstance(hint, type):
        return hint.__name__
    return str(hint).replace("typing.", "")


# ┌────────────┐
# │ Docstrings │
# └────────────┘


@dataclass
class ParamDoc:
    """What a numpy docstring says about one parameter"""

    type: str = ""
    description: str = ""


_SECTION_RE = re.compile(r"^\s*(\w[\w ]*)\n\s*-{3,}\s*$", re.MULTILINE)


def parse_numpy_doc(doc: str | None) -> tuple[str, dict[str, ParamDoc]]:
    """
    Return the summary of a numpy docstring and its Parameters section

    ``name : type`` lines start a parameter, the indented lines below describe it.
    ``a, b, c`` documents several parameters at once
    """
    if not doc:
        return "", {}
    doc = inspect.cleandoc(doc)
    lines = doc.splitlines()
    summary_lines: list[str] = []
    for line in lines:
        if not line.strip():
            if summary_lines:
                break
            continue
        if re.match(r"^\s*-{3,}\s*$", line):
            summary_lines = summary_lines[:-1]
            break
        summary_lines.append(line.strip())
    summary = " ".join(summary_lines)

    params: dict[str, ParamDoc] = {}
    in_params = False
    current: list[ParamDoc] = []
    for i, line in enumerate(lines):
        next_line = lines[i + 1] if i + 1 < len(lines) else ""
        if re.match(r"^\s*-{3,}\s*$", next_line) and line.strip():
            in_params = line.strip().lower() in ("parameters", "other parameters")
            current = []
            continue
        if re.match(r"^\s*-{3,}\s*$", line):
            continue
        if not in_params:
            continue
        if line and not line[0].isspace():
            names, _, type_str = line.partition(":")
            current = []
            for name in names.split(","):
                name = name.strip().lstrip("*")
                if name:
                    params[name] = ParamDoc(type=type_str.strip())
                    current.append(params[name])
        elif line.strip():
            for param in current:
                separator = " " if param.description else ""
                param.description += separator + line.strip()
    return summary, params


def doc_choices(type_str: str) -> list[str] | None:
    """Choices of a numpy type like ``{'TCP', 'UDP'}``"""
    match = re.search(r"\{([^}]*)\}", type_str)
    if match is None:
        return None
    choices = [c.strip().strip("'\"") for c in match.group(1).split(",")]
    return [c for c in choices if c] or None


# ┌────────────┐
# │ Parameters │
# └────────────┘


class FieldType(StrEnum):
    """Editor used for a value parameter"""

    BOOL = "bool"
    INT = "int"
    FLOAT = "float"
    STR = "str"
    BYTES = "bytes"
    TEXT = "str | bytes"
    CHOICE = "choice"
    STOP_CONDITIONS = "stop-conditions"
    EXPRESSION = "expression"
    UNSUPPORTED = "unsupported"


@dataclass
class ParamSpec:
    """One parameter of a constructor or of a method"""

    name: str
    annotation: Any
    default: Any
    kind: inspect._ParameterKind
    doc: ParamDoc = field(default_factory=ParamDoc)
    # Slot : the parameter is another component (the layer below, a driver, ...)
    is_slot: bool = False
    # Field : the parameter is a value
    field_type: FieldType = FieldType.UNSUPPORTED
    choices: list[Any] | None = None
    allows_default: bool = False
    allows_none: bool = False
    # Name of a static method listing suggestions (SerialPort.list_ports, ...)
    suggestions: Callable[[], list[str]] | None = None

    @property
    def has_default(self) -> bool:
        """True if the parameter can be left out"""
        return self.default is not inspect.Parameter.empty

    @property
    def required(self) -> bool:
        """True if a value must be given"""
        return not self.has_default

    @property
    def hidden(self) -> bool:
        """Parameters the GUI can't edit but can leave out (sock, callbacks, ...)"""
        return self.field_type is FieldType.UNSUPPORTED and not self.is_slot and self.has_default

    @property
    def type_label(self) -> str:
        """Type as shown to the user"""
        return type_name(self.annotation) or self.doc.type

    def accepts(self, cls: type) -> bool:
        """True if the slot accepts an instance of cls"""
        return self.is_slot and accepts(self.annotation, cls)


def _classify_member(hint: Any) -> tuple[FieldType, list[Any] | None]:
    if hint is bool:
        return FieldType.BOOL, None
    if hint is int:
        return FieldType.INT, None
    if hint is float:
        return FieldType.FLOAT, None
    if hint is str:
        return FieldType.STR, None
    if hint is bytes:
        return FieldType.BYTES, None
    if isinstance(hint, type) and issubclass(hint, enum.Enum):
        return FieldType.CHOICE, list(hint)
    origin = get_origin(hint)
    if origin is Literal:
        return FieldType.CHOICE, list(get_args(hint))
    if isinstance(hint, type) and issubclass(hint, StopCondition):
        return FieldType.STOP_CONDITIONS, None
    if origin in (list, tuple) and get_args(hint):
        inner = get_args(hint)[0]
        if isinstance(inner, type) and issubclass(inner, StopCondition):
            return FieldType.STOP_CONDITIONS, None
    if origin in (list, tuple, dict, set) or hint in (list, tuple, dict, set, complex):
        return FieldType.EXPRESSION, None
    return FieldType.UNSUPPORTED, None


def _classify(spec: ParamSpec) -> None:
    hint = spec.annotation
    if hint is inspect.Parameter.empty:
        # No type hint : the default value tells what it is, else a python expression
        if spec.has_default and spec.default is not None:
            hint = type(spec.default)
        else:
            spec.field_type = FieldType.EXPRESSION
            return

    if _mentions_component(hint):
        spec.is_slot = True
        spec.allows_none = type(None) in (_union_members(hint) or [])
        return

    members = _union_members(hint) or [hint]
    kept: list[tuple[FieldType, list[Any] | None]] = []
    for member in members:
        if member is types.NoneType or member is None:
            spec.allows_none = True
        elif get_origin(member) is Literal and DEFAULT in get_args(member):
            spec.allows_default = True
        else:
            kept.append(_classify_member(member))

    types_found = {t for t, _ in kept if t is not FieldType.UNSUPPORTED}
    if not types_found:
        spec.field_type = FieldType.UNSUPPORTED
    elif types_found == {FieldType.STR, FieldType.BYTES}:
        spec.field_type = FieldType.TEXT
    elif types_found <= {FieldType.INT, FieldType.FLOAT}:
        spec.field_type = FieldType.FLOAT if FieldType.FLOAT in types_found else FieldType.INT
    elif FieldType.STOP_CONDITIONS in types_found:
        spec.field_type = FieldType.STOP_CONDITIONS
    elif types_found == {FieldType.CHOICE, FieldType.STR}:
        # Endian | str : the enum gives the choices, a string is accepted too
        spec.field_type = FieldType.CHOICE
        spec.choices = next(c for t, c in kept if t is FieldType.CHOICE)
    elif len(types_found) == 1:
        spec.field_type = types_found.pop()
        spec.choices = next(c for t, c in kept if t is spec.field_type)
    else:
        spec.field_type = FieldType.EXPRESSION

    if spec.field_type is FieldType.UNSUPPORTED and not spec.has_default:
        # Required and of a type the GUI has no editor for : a python expression
        spec.field_type = FieldType.EXPRESSION

    if spec.field_type is FieldType.STR:
        choices = doc_choices(spec.doc.type)
        if choices:
            spec.field_type = FieldType.CHOICE
            spec.choices = choices


def _typevar_mapping(cls: type | None) -> dict[Any, Any]:
    """
    What the TypeVars of the library bases stand for in cls : AdapterT is bytes in
    Protocol.write_raw(data: AdapterT) once it is called on SCPI
    """
    mapping: dict[Any, Any] = {}
    if cls is None:
        return mapping
    for base in (Adapter, AsyncAdapter, Protocol, AsyncProtocol):
        if isinstance(cls, type) and issubclass(cls, base):
            args = generic_args(cls, base) or ()
            parameters = getattr(base, "__parameters__", ())
            for var, arg in zip(parameters, args, strict=False):
                if not isinstance(arg, TypeVar):
                    mapping[var] = arg
    return mapping


def _deep_substitute(hint: Any, mapping: dict[Any, Any]) -> Any:
    if not mapping:
        return hint
    if isinstance(hint, TypeVar):
        return mapping.get(hint, hint)
    members = _union_members(hint)
    if members is not None:
        result = None
        for member in members:
            member = _deep_substitute(member, mapping)
            result = member if result is None else result | member
        return result
    return hint


def _resolve_hints(func: Callable[..., Any], owner: type | None) -> dict[str, Any]:
    module = sys.modules.get(getattr(func, "__module__", ""), None)
    globalns = dict(vars(module)) if module is not None else {}
    localns = dict(vars(owner)) if owner is not None else None
    try:
        return get_type_hints(func, globalns=globalns, localns=localns)
    except Exception:  # pylint: disable=broad-exception-caught
        pass
    # One unresolvable hint mustn't lose the others
    hints: dict[str, Any] = {}
    for name, annotation in getattr(func, "__annotations__", {}).items():
        if isinstance(annotation, str):
            try:
                annotation = eval(annotation, globalns, localns)  # pylint: disable=eval-used
            except Exception:  # pylint: disable=broad-exception-caught
                annotation = inspect.Parameter.empty
        hints[name] = annotation
    return hints


def _list_suggestions(owner: type, spec: ParamSpec, first_str: bool) -> Callable[[], list[str]] | None:
    """
    A static method listing the values of the parameter : list_ports for 'port', or the
    only list_* method for the first text parameter (Visa.list_devices)
    """
    candidates = []
    for name in dir(owner):
        if not name.startswith("list_"):
            continue
        raw = inspect.getattr_static(owner, name, None)
        if isinstance(raw, staticmethod):
            candidates.append(name)
    for name in candidates:
        if name == f"list_{spec.name}s":
            return getattr(owner, name)  # type: ignore[no-any-return]
    if first_str and len(candidates) == 1:
        return getattr(owner, candidates[0])  # type: ignore[no-any-return]
    return None


def signature_params(
    func: Callable[..., Any],
    owner: type | None,
    docs: dict[str, ParamDoc],
) -> list[ParamSpec]:
    """Parameters of a function, self/cls and *args/**kwargs left out"""
    try:
        signature = inspect.signature(func)
    except (TypeError, ValueError):
        return []
    mapping = _typevar_mapping(owner)
    hints = {k: _deep_substitute(v, mapping) for k, v in _resolve_hints(func, owner).items()}
    params: list[ParamSpec] = []
    first_str_seen = False
    for i, param in enumerate(signature.parameters.values()):
        if i == 0 and param.name in ("self", "cls"):
            continue
        if param.kind in (param.VAR_POSITIONAL, param.VAR_KEYWORD):
            continue
        spec = ParamSpec(
            name=param.name,
            annotation=hints.get(param.name, param.annotation),
            default=param.default,
            kind=param.kind,
            doc=docs.get(param.name, ParamDoc()),
        )
        _classify(spec)
        if owner is not None and spec.field_type is FieldType.STR:
            spec.suggestions = _list_suggestions(owner, spec, not first_str_seen)
            first_str_seen = True
        params.append(spec)
    return params


# ┌────────────┐
# │ Components │
# └────────────┘


@dataclass
class ComponentInfo:
    """Everything the GUI shows about a component class"""

    cls: type
    kind: Kind
    summary: str
    params: list[ParamSpec]
    # Type the component hands to the layer above (bytes for IP, str for SCPI)
    provides: Any

    @property
    def name(self) -> str:
        """Class name"""
        return self.cls.__name__

    @property
    def qualified_name(self) -> str:
        """module:Class, used to save a stack"""
        return f"{self.cls.__module__}:{self.cls.__qualname__}"

    @property
    def slots(self) -> list[ParamSpec]:
        """Parameters that are other components"""
        return [p for p in self.params if p.is_slot]

    @property
    def fields(self) -> list[ParamSpec]:
        """Parameters that are values the user can edit"""
        return [p for p in self.params if not p.is_slot and not p.hidden]

    @property
    def is_async(self) -> bool:
        """True for the async facades"""
        return is_async(self.cls)

    @property
    def is_base_class(self) -> bool:
        """
        True for a driver whose open/close/test are still abstract (SCPIDriver) : it is
        usable, but meant to be subclassed
        """
        return any(
            getattr(inspect.getattr_static(self.cls, name, None), "__isabstractmethod__", False)
            for name in ("open", "close", "test")
        )

    @property
    def code_only(self) -> str:
        """
        Why the component can't be used in the GUI, empty if it can : an adapter must
        hand out data (str or bytes) to be tested or stacked under a protocol. An
        IPServer hands out an IP adapter per client
        """
        if self.kind is Kind.ADAPTER and self.provides not in (str, bytes):
            return (
                f"{self.name} hands out {self.provides_label} objects, not data : "
                "use it from your code, not in the UI"
            )
        return ""

    @property
    def provides_label(self) -> str:
        """What flows to the layer above"""
        if self.kind in (Kind.DRIVER, Kind.SUBDRIVER):
            return "commands"
        return type_name(self.provides) or "?"


def _provides(cls: type, kind: Kind) -> Any:
    base: type
    if kind is Kind.ADAPTER:
        base = AsyncAdapter if issubclass(cls, AsyncAdapter) else Adapter
        args = generic_args(cls, base)
        return args[1] if args else None
    if kind is Kind.PROTOCOL:
        base = AsyncProtocol if issubclass(cls, AsyncProtocol) else Protocol
        args = generic_args(cls, base)
        return args[2] if args else None
    return cls


def _class_docs(cls: type) -> tuple[str, dict[str, ParamDoc]]:
    summary, params = parse_numpy_doc(cls.__doc__)
    init_summary, init_params = parse_numpy_doc(getattr(cls, "__init__", None).__doc__)
    # An async facade documented as "same parameters as X" takes the sync ones
    if not params and is_async(cls):
        sync = getattr(sys.modules.get(cls.__module__), cls.__name__.removeprefix("Async"), None)
        if isinstance(sync, type) and sync is not cls:
            _, params = parse_numpy_doc(sync.__doc__)
    return summary or init_summary, {**params, **init_params}


@cache
def component_info(cls: type) -> ComponentInfo:
    """Introspect a component class (cached)"""
    kind = kind_of(cls)
    if kind is None:
        raise TypeError(f"{cls!r} is not an adapter, a protocol or a driver")
    summary, docs = _class_docs(cls)
    init = vars(cls).get("__init__") or next(
        (vars(c)["__init__"] for c in cls.__mro__ if "__init__" in vars(c)), object.__init__
    )
    params = [] if init is object.__init__ else signature_params(init, cls, docs)
    return ComponentInfo(
        cls=cls,
        kind=kind,
        summary=summary,
        params=params,
        provides=_provides(cls, kind),
    )


# ┌──────────┐
# │ Commands │
# └──────────┘


@dataclass
class CommandInfo:
    """A method of a component, as a command of the test screen"""

    name: str
    owner: type
    summary: str
    params: list[ParamSpec]
    returns: Any
    is_framework: bool = False

    @property
    def returns_label(self) -> str:
        """Return type as shown to the user"""
        if self.returns in (None, type(None), inspect.Parameter.empty):
            return ""
        return type_name(self.returns)

    @property
    def signature(self) -> str:
        """name(a: int, b: str = '') -> ret"""
        parts = []
        for p in self.params:
            text = p.name
            if p.type_label:
                text += f": {p.type_label}"
            if p.has_default:
                text += f" = {p.default!r}"
            parts.append(text)
        ret = f" → {self.returns_label}" if self.returns_label else ""
        return f"{self.name}({', '.join(parts)}){ret}"


# What the library facades offer on top of read/write/query, which the I/O panel covers
_FRAMEWORK_COMMANDS: dict[type, list[str]] = {
    Adapter: ["set_timeout", "set_stop_conditions", "clear_read_buffer"],
    AsyncAdapter: ["set_timeout", "set_stop_conditions", "clear_read_buffer"],
    Protocol: ["set_timeout", "write_raw", "clear_buffer"],
    AsyncProtocol: ["set_timeout", "write_raw", "clear_buffer"],
}

# Handled by the toolbar
_TOOLBAR_COMMANDS = {"open", "close"}


def _command_info(cls: type, owner: type, name: str, framework: bool) -> CommandInfo | None:
    raw = inspect.getattr_static(owner, name, None)
    if isinstance(raw, (staticmethod, classmethod)):
        func = raw.__func__
    elif inspect.isfunction(raw):
        func = raw
    else:
        return None
    if getattr(func, "__isabstractmethod__", False):
        return None
    summary, docs = parse_numpy_doc(func.__doc__)
    hints = _resolve_hints(func, owner)
    returns = _deep_substitute(hints.get("return", inspect.Parameter.empty), _typevar_mapping(cls))
    return CommandInfo(
        name=name,
        owner=owner,
        summary=summary,
        params=signature_params(func, cls, docs),
        returns=returns,
        is_framework=framework,
    )


@cache
def commands_of(cls: type) -> list[CommandInfo]:
    """
    Public methods of a component, the ones of the classes above the library bases first

    For a driver deriving from SCPIDriver, that's its own methods then the SCPIDriver
    ones (get_identification, reset, ...). Adapters and protocols add a few methods of
    the library facades (set_timeout, ...)
    """
    commands: list[CommandInfo] = []
    seen: set[str] = set(_TOOLBAR_COMMANDS)
    for owner in cls.__mro__:
        if owner in FRAMEWORK_BASES or owner is object:
            break
        if owner.__module__ in ("typing", "abc", "builtins"):
            continue
        for name, _ in vars(owner).items():
            if name.startswith("_") or name in seen:
                continue
            seen.add(name)
            info = _command_info(cls, owner, name, False)
            if info is not None:
                commands.append(info)
    for base, names in _FRAMEWORK_COMMANDS.items():
        if issubclass(cls, base):
            for name in names:
                if name in seen:
                    continue
                seen.add(name)
                owner = next(c for c in cls.__mro__ if name in vars(c))
                info = _command_info(cls, owner, name, True)
                if info is not None:
                    commands.append(info)
    return commands


@cache
def properties_of(cls: type) -> list[str]:
    """Public properties, shown as the state of a component"""
    names = []
    for owner in reversed(cls.__mro__):
        if owner is object:
            continue
        for name, value in vars(owner).items():
            if isinstance(value, property) and not name.startswith("_") and name not in names:
                names.append(name)
    hidden = {"engine", "frame_buffer"}
    return [n for n in names if n not in hidden]


def io_payload_type(cls: type) -> type | None:
    """
    Payload type of the read/write/query of an adapter or a protocol, if the I/O panel
    can edit it (str or bytes). Modbus (ModbusSDU) only gets its commands
    """
    kind = kind_of(cls)
    if kind not in (Kind.ADAPTER, Kind.PROTOCOL):
        return None
    provides = component_info(cls).provides
    if provides in (str, bytes):
        return provides  # type: ignore[no-any-return]
    return None


# ┌────────────────────┐
# │ Runtime discovery  │
# └────────────────────┘


@dataclass
class Discovered:
    """A component found inside another one, once built"""

    path: str
    instance: Any


def discover_components(obj: Any) -> list[Discovered]:
    """
    Components an instance holds in its attributes : the protocol a driver built for
    itself (SCPIDriver._prot), the sub-drivers it exposes (self.channels = [...]) ...

    Lists, tuples and dicts are looked into, one level deep
    """
    found: list[Discovered] = []
    try:
        attributes = dict(vars(obj))
    except TypeError:
        return found
    for name, value in attributes.items():
        if is_component(value):
            found.append(Discovered(name, value))
        elif isinstance(value, (list, tuple)):
            for i, item in enumerate(value):
                if is_component(item):
                    found.append(Discovered(f"{name}[{i}]", item))
        elif isinstance(value, dict):
            for key, item in value.items():
                if is_component(item):
                    found.append(Discovered(f"{name}[{key!r}]", item))
    return found


def returned_components(value: Any) -> list[Discovered]:
    """Components returned by a command (a sub-driver, a client of an IPServer, ...)"""
    if is_component(value):
        return [Discovered("", value)]
    if isinstance(value, (list, tuple)):
        return [Discovered(f"[{i}]", v) for i, v in enumerate(value) if is_component(v)]
    if isinstance(value, dict):
        return [Discovered(f"[{k!r}]", v) for k, v in value.items() if is_component(v)]
    return []
