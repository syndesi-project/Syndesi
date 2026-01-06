# File : errors.py
# Author : Sébastien Deriaz
# License : GPL
"""
Syndesi errors
"""

from pathlib import Path

from syndesi.tools.types import NumberLike

PACKAGE_PATH = Path(__file__).resolve().parent.parent


class SyndesiError(Exception):
    """Base class for all Syndesi errors"""


class AdapterError(SyndesiError):
    """Adapter error"""


class AdapterConfigurationError(AdapterError):
    """Adapter configuration error"""


class AdapterOpenError(AdapterError):
    """Adapter failed to open"""


class AdapterWriteError(AdapterError):
    """Adapter failed to write"""


class AdapterDisconnected(AdapterError):
    """Adapter disconnected"""


class WorkerThreadError(AdapterError):
    """Adapters worker thread error"""


class AdapterReadError(AdapterError):
    """Error while performing read operation"""


class ProtocolError(SyndesiError):
    """Protocol error"""


class ProtocolWriteError(SyndesiError):
    """Protocol error when writing"""


class ProtocolReadError(SyndesiError):
    """Protocol error when reading"""


class AdapterTimeoutError(AdapterError):
    """
    Adapter timeout error
    """

    def __init__(self, timeout: NumberLike) -> None:
        self.timeout = timeout
        super().__init__(
            f"No response received from target within {self.timeout} seconds"
        )
