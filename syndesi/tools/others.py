# File : others.py
# Author : Sébastien Deriaz
# License : GPL

from enum import Enum
from typing import Final, Literal


class _Default(Enum):
    DEFAULT = "DEFAULT"

    def __repr__(self) -> str:
        return "DEFAULT"


DEFAULT: Final = _Default.DEFAULT
"""Not given : the object uses its default, and knows it wasn't chosen"""

DefaultType = Literal[_Default.DEFAULT]
