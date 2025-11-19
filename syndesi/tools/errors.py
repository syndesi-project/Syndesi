# File : errors.py
# Author : Sébastien Deriaz
# License : GPL

from pathlib import Path

from syndesi.tools.types import NumberLike

PACKAGE_PATH = Path(__file__).resolve().parent.parent


class SyndesiError(Exception):
    """Base class for all Syndesi errors"""


class BackendCommunicationError(SyndesiError):
    """Error with backend communication"""


class BackendError(SyndesiError):
    """Error inside the backend"""


class AdapterError(SyndesiError):
    """Adapter error"""

class AdapterConfigurationError(AdapterError):
    """Adapter configuration error"""

class AdapterFailedToOpen(AdapterError):
    """Adapter failed to open"""


class AdapterDisconnected(AdapterError):
    """Adapter disconnected"""


class ProtocolError(SyndesiError):
    """Protocol error"""


class AdapterTimeoutError(AdapterError):
    def __init__(self, timeout: NumberLike) -> None:
        self.timeout = timeout
        super().__init__(
            f'No response received from device within {self.timeout} seconds"'
        )


def make_error_description(e: Exception) -> str:
    tb = e.__traceback__
    if tb is None:
        error_message = ""
    else:
        while True:
            if tb.tb_next is None:
                break
            file = Path(tb.tb_next.tb_frame.f_code.co_filename).resolve()
            if not file.is_relative_to(PACKAGE_PATH):
                break
            tb = tb.tb_next

        _type = type(e)
        extra_arguments = (str(e),)
        frame = tb.tb_frame
        line_no = tb.tb_lineno
        filename = frame.f_code.co_filename
        error_message = f"{_type} : {extra_arguments} {filename}:{line_no}"

    return error_message
