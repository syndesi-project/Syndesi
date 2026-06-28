# File : protocol.py
# Author : Sébastien Deriaz
# License : GPL

from typing import Generic, TypeVar
from .tools import Block
from ..protocols.protocol import Protocol

ProtocolT = TypeVar("ProtocolT", bound=Protocol)

class ProtocolBlock(Generic[ProtocolT], Block):
    _protocol : ProtocolT

