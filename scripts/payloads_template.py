"""
THIS FILE IS GENERATED AUTOMATICALLYDO NOT EDIT
This file has been written by the script >>>file<<<
date : >>>date<<<
"""

from typing import TypedDict
from construct import *
from enum import Enum
from dataclasses import dataclass

>>>endian<<<

class Commands(Enum):
>>>commands<<<

@dataclass
class Payload():
    def value(self) -> bytearray:
        """
        Return bytearray value of the frame    

        Returns
        -------
        output : bytearray
        """
        raise NotImplementedError("Cannot use function directly")

    def parse(self, buffer : bytearray):
        """
        Parse frame from a bytearray buffer

        Parameters
        ----------
        buffer : bytearray
        """
        raise NotImplementedError("Cannot use function directly")

>>>payloads<<<


class PayloadMatch(TypedDict):
    command: Commands
    payload : Payload

payload_match : PayloadMatch = {
>>>payload_match<<<
}

class SpecialValues(Enum):
>>>special_values<<<