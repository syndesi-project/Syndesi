# File : errors.py
# Author : Sébastien Deriaz
# License : GPL

from pathlib import Path

PACKAGE_PATH = Path(__file__).resolve().parent.parent


class SyndesiError(Exception):
    """Base class for all Syndesi errors"""


class BackendCommunicationError(SyndesiError):
    """Error with backend communication"""


class BackendError(SyndesiError):
    """Error inside the backend"""


class AdapterBackendError(BackendError):
    """Error inside an adapter backend"""


class AdapterError(SyndesiError):
    """Error inside an adapter frontend"""


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
