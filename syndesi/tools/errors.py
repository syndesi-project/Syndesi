# File : errors.py
# Author : Sébastien Deriaz
# License : GPL
"""
Syndesi errors
"""

from pathlib import Path

PACKAGE_PATH = Path(__file__).resolve().parent.parent


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


class AdapterTimeoutError(AdapterReadError):
    """
    Adapter timeout error
    """

    def __init__(self, timeout: float) -> None:
        self.timeout = timeout
        super().__init__(
            f"No response received from target within {self.timeout} seconds"
        )


# ┌──────────┐
# │ Protocol │
# └──────────┘


class ProtocolError(SyndesiError):
    """Protocol error"""


class ProtocolWriteError(ProtocolError):
    """The protocol could not encode a payload"""


class ProtocolReadError(ProtocolError):
    """The protocol could not decode what it received"""
