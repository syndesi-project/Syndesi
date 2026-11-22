# File : errors.py
# Author : Sébastien Deriaz
# License : GPL
"""
Syndesi errors

Every error derives from SyndesiError :

    from syndesi.errors import AdapterTimeoutError
"""

from typing import Any


class SyndesiError(Exception):
    """Base class for all Syndesi errors"""


# ┌─────────┐
# │ Backend │
# └─────────┘


class BackendError(SyndesiError):
    """Base class for every backend error. The engine turns these into adapter errors"""


class BackendDisconnectedError(BackendError):
    """The target closed the connection"""


class BackendOpenError(BackendError):
    """The backend could not be opened"""


class BackendWriteError(BackendError):
    """The backend could not write, or could not write everything"""


class BackendReadError(BackendError):
    """The backend could not read"""


# ┌─────────┐
# │ Adapter │
# └─────────┘


class AdapterError(SyndesiError):
    """Adapter error"""


class AdapterConfigurationError(AdapterError):
    """Adapter configuration error"""


class AdapterOpenError(AdapterError):
    """Adapter failed to open"""


class AdapterWriteError(AdapterError):
    """Adapter failed to write"""


class AdapterDisconnectedError(AdapterError):
    """Adapter disconnected"""


class WorkerThreadError(AdapterError):
    """Adapters worker thread error"""


class AdapterReadError(AdapterError):
    """Error while performing read operation"""


_RECEIVED_PREVIEW_LENGTH = 64


class AdapterTimeoutError(AdapterReadError):
    """
    No valid frame arrived within the timeout

    Parameters
    ----------
    timeout : float
    received : Any
        What arrived without forming a valid frame (the start of an answer whose
        terminator never came, ...), None if nothing arrived at all
    waiting_for : str
        What would have completed the frame, the stop-conditions for instance
    """

    def __init__(
        self, timeout: float, received: Any = None, waiting_for: str = ""
    ) -> None:
        self.timeout = timeout
        self.received = received
        if received is None:
            message = f"No response received from target within {timeout} seconds"
        else:
            message = (
                f"No valid frame received within {timeout} seconds, but already "
                f"received {_preview(received)}"
            )
            if waiting_for:
                message += f", waiting for {waiting_for}"
        super().__init__(message)


def _preview(data: Any) -> str:
    """Short representation of received data, long enough to recognize it"""
    if isinstance(data, bytes):
        shown = data[:_RECEIVED_PREVIEW_LENGTH]
        ellipsis = "..." if len(data) > len(shown) else ""
        unit = "byte" if len(data) == 1 else "bytes"
        return f"{shown!r}{ellipsis} ({len(data)} {unit})"
    return repr(data)


# ┌──────────┐
# │ Protocol │
# └──────────┘


class ProtocolError(SyndesiError):
    """Protocol error"""


class ProtocolWriteError(ProtocolError):
    """The protocol could not encode a payload"""


class ProtocolReadError(ProtocolError):
    """The protocol could not decode what it received"""
