# File : timeout.py
# Author : Sébastien Deriaz
# License : GPL

from enum import Enum
from types import EllipsisType
from typing import Any, Protocol

from ..tools.types import NumberLike, is_number

# from .backend.timeout import TimeoutAction, JsonKey


class TimeoutAction(Enum):
    ERROR = "error"
    RETURN = "return"


class IsInitialized(Protocol):
    response: NumberLike | None


class Timeout:
    DEFAULT_ACTION = TimeoutAction.ERROR

    def __init__(
        self,
        response: NumberLike | None | EllipsisType = ...,
        action: str | EllipsisType | TimeoutAction = ...,
    ) -> None:
        """
        This class holds timeout information

        Parameters
        ----------
        response : float
            Time before the device responds
        action : str
            Action performed when a timeout occurs. 'error' -> raise an error, 'return' -> return b''
        """
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
        if self._is_default_response:
            self._response = default_timeout.response()
        if self._is_default_action:
            self.action = default_timeout.action

    def response(self) -> NumberLike | None:
        if self._response is ...:
            return None
        elif self._response is None:
            return None
        else:
            return self._response
        
    def is_initialized(self) -> bool:
        return not self._response is Ellipsis



def any_to_timeout(value: Any) -> Timeout:
    if value is None:
        return Timeout(response=None)
    elif is_number(value):
        return Timeout(response=float(value))
    elif isinstance(value, Timeout):
        return value
    else:
        raise ValueError(f"Could not convert {value} to Timeout")


# class TimeoutException(Exception):
#     def __init__(self, value: NumberLike, limit: NumberLike) -> None:
#         super().__init__()
#         self._value = value
#         self._limit = limit

#     def __str__(self) -> str:
#         try:
#             value_string = f"{self._value * 1e3:.3f}ms"
#         except (ValueError, TypeError):
#             value_string = "not received"

#         try:
#             limit_string = f"{self._limit * 1e3:.3f}ms"
#         except (ValueError, TypeError):
#             limit_string = "not received"

#         return f"{value_string} / {limit_string}"

#     def __repr__(self) -> str:
#         return self.__str__()
