# File : timeout.py
# Author : Sébastien Deriaz
# License : GPL
"""
This module holds the Timeout class, this class is meant for the user as a frontend for the
backend timeout management
"""

from enum import Enum
from types import EllipsisType
from typing import Any

from ..tools.types import NumberLike, is_number


class TimeoutAction(Enum):
    """
    Action on timeout expiration
    """

    ERROR = "error"
    RETURN_EMPTY = "return_empty"
    RETURN_NONE = "return_none"


class Timeout:
    """
    This class holds timeout information

    Parameters
    ----------
    response : float
        Time before the device responds
    action : str
        Action performed when a timeout occurs
        * ``error`` : raise a AdapterTimeoutError
        * ``return_empty`` : return b''
        * ``return_none`` : return None
    """

    DEFAULT_ACTION = TimeoutAction.ERROR

    def __init__(
        self,
        response: NumberLike | None | EllipsisType = ...,
        action: str | EllipsisType | TimeoutAction = ...,
    ) -> None:

        super().__init__()

        self._is_default_response = response is ...
        self._is_default_action = action is ...

        self.action: EllipsisType | TimeoutAction
        if action is ...:
            self.action = self.DEFAULT_ACTION
        else:
            self.action = TimeoutAction(action)

        self._response: EllipsisType | NumberLike | None = response

    def __str__(self) -> str:
        if self._response is ...:
            r = "..."
        else:
            r = f"{self._response:.3f}"
        if self.action is ...:
            a = "..."
        else:
            a = f"{self.action}"
        return f"Timeout({r}:{a})"

    def __repr__(self) -> str:
        return self.__str__()

    def set_default(self, default_timeout: "Timeout") -> None:
        """
        Set the default timeout (no effect if timeout is already set)

        Parameters
        ----------
        default_timeout : Timeout
        """
        if self._is_default_response:
            self._response = default_timeout.response()
        if self._is_default_action:
            self.action = default_timeout.action

    def response(self) -> NumberLike | None:
        """
        Return timeout response if it has been configured

        Returns
        -------
        response : NumberLike | None
        """
        if self._response is ...:
            return None
        if self._response is None:
            return None
        return self._response

    def is_initialized(self) -> bool:
        """
        Return True if the Timeout has been initialized, False otherwise
        """
        return self._response is not Ellipsis


def any_to_timeout(value: Any) -> Timeout:
    """
    Convert any input to a timeout (if possible)

    Parameters
    ----------
    value : None | NumberLike | Timeout

    Returns
    -------
    timeout : Timeout
    """
    if value is None:
        return Timeout(response=None)
    if is_number(value):
        return Timeout(response=float(value))
    if isinstance(value, Timeout):
        return value
    raise ValueError(f"Could not convert {value} to Timeout")
