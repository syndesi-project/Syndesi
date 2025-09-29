# File : exceptions
# Author : Sébastien Deriaz
# License : GPL


class SyndesiException(Exception):
    def __init__(self, *args: object) -> None:
        """
        Syndesi base exception class
        """
        super().__init__(*args)


class SyndesiTimeoutException(SyndesiException):
    def __init__(self, *args: object) -> None:
        super().__init__(*args)
