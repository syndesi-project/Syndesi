
from pyvisa import ResourceManager, VisaIOError
from pyvisa.resources import Resource
import socket
from .timed_queue import TimedQueue
from .adapter import Adapter
from ..tools.types import to_bytes
from typing import Union
from threading import Thread

class VISA(Adapter):
    def __init__(self, resource : str):
        """
        USB VISA stack adapter

        Parameters
        ----------
        resource : str
            resource address string
        """
        self._resource = resource
        self._rm = ResourceManager()
        self._inst : Resource
        self._inst = self._rm.open_resource(self._resource)
        self._inst.write_termination = ''
        self._inst.read_termination = ''

    def list_devices(self=None):
        """
        Returns a list of available VISA devices
        """
        # To list available devices only and not previously connected ones,
        # each device will be opened and added to the list only if that succeeded
        rm = ResourceManager()

        available_resources = []
        for device in rm.list_resources():
            try:
                d = rm.open_resource(device)
                d.close()
                available_resources.append(device)
            except VisaIOError:
                pass

        return available_resources

    def flushRead(self):
        pass

    def open(self):
        self._inst.open()

    def close(self):
        self._inst.close()
            
    def write(self, data : Union[bytes, str]):
        data = to_bytes(data)
        self._inst.write_raw(data)

    def _start_thread(self):
        super()._start_thread()
        if self._thread is None or not self._thread.is_alive():
            self._thread = Thread(target=self._read_thread, daemon=True, args=(self._socket, self._read_queue, self._thread_stop_read))
            self._thread.start()


    def _read_thread(self, socket : socket.socket, read_queue : TimedQueue, stop : socket.socket):
        self._inst.timeout = 0.05
        stop.setblocking(False)
        while True:
            if(stop.recv(1)):
                break
            else:
                try:
                    payload = self._inst.read_raw()
                except TimeoutError: # TODO : Check if this is the error raised when a timeout occurs
                    pass
                else:
                    read_queue.put(payload)

    # def read(self) -> bytes:
    #     return self._inst.read_raw()

    def query(self, data : Union[bytes, str], timeout=None, continuation_timeout=None) -> bytes:
        """
        Shortcut function that combines
        - flush_read
        - write
        - read
        """
        # TODO : implement timeouts
        self.write(data)
        return self.read()