# remote.py
# Sébastien Deriaz
# 09.04.2024
#
# The remote adapter allows for commands to be issued on a different device through TCP
# The goal is to istanciate a class as such :
#
# Only adapter :
#   # The remote computer is accessed with 192.168.1.1
#   # The device (connected to the remote computer) is accessed with 192.168.2.1
#   my_adapter = Remote('192.168.1.1', IP('192.168.2.1'))
#
# Protocol :
#   my_protocol = SCPI(Remote('192.168.1.1', Serial('/dev/ttyUSB0')))
#
#
# Driver :
#   my_device = Driver(Remote('192.168.1.1', VISA('...')))
from .adapter import Adapter
from . import IP, SerialPort, VISA
from enum import Enum
from ..tools.remote_api import *
from typing import Union

DEFAULT_PORT = 2608

class Remote(Adapter):
    def __init__(self, proxy_adapter : Adapter, remote_adapter : Adapter):
        """
        Remote adapter

        Parameters
        ----------
        proxy_adapter : Adapter
            Adapter to connect to the remote server
        remote_adapter : Adapter
            Adapter to instanciate on the remote server
        """
        super().__init__()

        self._proxy = proxy_adapter
        self._remote = remote_adapter

        if isinstance(proxy_adapter, IP):
            proxy_adapter.set_default_port(DEFAULT_PORT)

        if isinstance(self._remote, IP):
            data = IPAdapterInstanciate(
                address=self._remote._address,
                port=self._remote._port,
                transport=self._remote._transport,
                buffer_size=self._remote._buffer_size
            ).encode()
            print(f"Data : {data}")
            self._proxy.query(data)

    def check(self, status : ReturnStatus):
        if not status.success:
            # There is an error
            raise RemoteException(status.error_message)

    def open(self):
        if isinstance(self._remote, IP):
            self._proxy.query(AdapterOpen().encode())

    def close(self):
        self._proxy.query(AdapterClose().encode())

    def write(self, data : Union[bytes, str]):
        self._proxy.query(AdapterWrite(data).encode())

    def read(self, timeout=None, stop_condition=None, return_metrics : bool = False):
        output : AdapterReadReturn
        output = parse(self._proxy.query(AdapterRead().encode()))
        if isinstance(output, AdapterReadReturn):
            return output.data
        elif isinstance(output, ReturnStatus):
            raise RemoteException(output.error_message)
        else:
            raise RuntimeError(f"Invalid return : {type(output)}")


    def query(self, data : Union[bytes, str], timeout=None, stop_condition=None, return_metrics : bool = False):
        self.check(parse(self._proxy.query(AdapterFlushRead().encode())))
        self.check(parse(self._proxy.query(AdapterWrite(data).encode())))
        return self.read(timeout=timeout, stop_condition=stop_condition, return_metrics=return_metrics)

    def _start_thread(self):
        pass
        

