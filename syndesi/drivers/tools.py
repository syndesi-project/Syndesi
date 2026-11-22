# File : tools.py
# Author : Sébastien Deriaz
# License : GPL
"""Syndesi Driver tools"""

from __future__ import annotations

import math
import re
import unicodedata
from collections.abc import Callable
from enum import StrEnum
from typing import Self

Accepted = str | int | float
"""A value a FlexibleEnum member accepts : text, or a number"""


def _text(value: str) -> str:
    # The micro sign µ and the greek μ look the same, NFKC makes them the same too
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", value))


def _number(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)  # '0.2', '+2.000000E-01'
        except ValueError:
            return None
    return None


class FlexibleEnum(StrEnum):
    """
    An enum with one value out, for the device, and several values in, for the user

    Each member is the value sent to the device, followed by the values it accepts:

    .. code-block:: python

        class VoltageRange(FlexibleEnum):
            _200mV = "200MV", 0.2, "200mV"
            _2V = "R1", 2, "2V"
            AUTO = "AUTO"

        VoltageRange("200 mv")      # VoltageRange._200mV
        VoltageRange(0.2)           # VoltageRange._200mV
        f"RANGE {VoltageRange(2)}"  # 'RANGE R1'

    A member accepts its value out, its name and the values listed after the value
    out. Text matches without spaces, and without case when that leaves only one
    member. Numbers match numbers and numeric text, such as the '+2.000000E-01' a
    device replies.

    A value no member accepts raises a ValueError. Two members accepting the same
    value is an error too, raised when the class is defined.

    Pass ``case_sensitive=True`` to match text only with its exact case:

    .. code-block:: python

        class Function(FlexibleEnum, case_sensitive=True):
            VOLTAGE = "VOLT"
    """

    # Members read each other's accepted values
    # pylint: disable=protected-access

    _accepted: tuple[Accepted, ...]
    # Set by __init_subclass__ : given a value here, it would be a member
    _case_sensitive: bool

    # Python calls __new__ only to create the members, VoltageRange(0.2) goes to
    # _missing_. Type checkers read VoltageRange(0.2) with this signature, so it is
    # typed as what a lookup accepts
    def __new__(cls, out: Self | str | float, *accepted: Accepted) -> Self:
        if not isinstance(out, str):
            raise TypeError(f"{cls.__name__} : the value out must be text, not {out!r}")
        member = str.__new__(cls, out)
        member._value_ = out
        member._accepted = accepted
        return member

    def __init_subclass__(
        cls, *, case_sensitive: bool = False, **kwargs: object
    ) -> None:
        super().__init_subclass__(**kwargs)
        cls._case_sensitive = case_sensitive
        # A value accepted by two members is a typo : say it when the class is written
        seen: dict[object, str] = {}
        for member in cls:
            for value in member._accepts():
                number = _number(value)
                key: object = _text(str(value)) if number is None else number
                if seen.get(key, member.name) != member.name:
                    raise TypeError(
                        f"{cls.__name__} : {value!r} is accepted by both "
                        f"{seen[key]} and {member.name}"
                    )
                seen[key] = member.name

    def _accepts(self) -> list[Accepted]:
        return [self.value, self.name, *self._accepted]

    @property
    def label(self) -> str:
        """The member for people : its first accepted text, else its value out"""
        return next((v for v in self._accepted if isinstance(v, str)), self.value)

    @classmethod
    def _missing_(cls, value: object) -> Self:
        ambiguous: list[Self] = []
        if isinstance(value, str):
            text = _text(value)
            found = cls._matching(lambda v: _text(v) == text)
            if not found and not cls._case_sensitive:
                found = cls._matching(lambda v: _text(v).casefold() == text.casefold())
            if len(found) == 1:
                return found[0]
            ambiguous = found
        number = _number(value)
        if number is not None:
            for member in cls:
                for accepted in member._accepts():
                    n = _number(accepted)
                    if n is not None and math.isclose(n, number, rel_tol=1e-9):
                        return member
        if ambiguous:
            raise ValueError(
                f"{value!r} could be {' or '.join(m.label for m in ambiguous)} "
                f"({cls.__name__}) : write it with its case"
            )
        raise ValueError(
            f"{value!r} is not a {cls.__name__}, use one of : "
            + ", ".join(m.label for m in cls)
        )

    @classmethod
    def _matching(cls, test: Callable[[str], bool]) -> list[Self]:
        """Members with an accepted text that passes test, in definition order"""
        return [
            m for m in cls if any(isinstance(v, str) and test(v) for v in m._accepts())
        ]
