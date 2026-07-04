# File : protocol.py
# Author : Sébastien Deriaz
# License : GPL

from typing import Generic, TypeVar

from syndesi.protocols.delimited import Delimited
from .tools import Block
from ..protocols.protocol import Protocol

ProtocolT = TypeVar("ProtocolT", bound=Protocol)

class ProtocolBlock(Generic[ProtocolT], Block):
    title : str = ""
    _protocol : ProtocolT


class DelimitedBlock(ProtocolBlock[Delimited]):
    title : str = "Delimited"
    
    def __init__(self, protocol : Delimited) -> None:
        super().__init__()
        self._protocol = protocol

    def build(self, parent: int | str) -> None:
        ...
