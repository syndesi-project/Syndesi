import socket
from enum import Enum
from .iadapter import IAdapter
from ..tools.types import assert_byte_instance
from .stop_conditions import Timeout
from threading import Thread
from .timed_queue import TimedQueue

DEFAULT_RESPONSE_TIMEOUT = 1
DEFAULT_CONTINUATION_TIMEOUT = 1e-3
DEFAULT_TOTAL_TIMEOUT = 5

class IP(IAdapter):
    class Protocol(Enum):
        TCP = 0
        UDP = 1
    def __init__(self,
                descriptor : str,
                port = None,
                transport : Protocol = Protocol.TCP,
                stop_condition=Timeout(
                    response=DEFAULT_RESPONSE_TIMEOUT,
                    continuation=DEFAULT_CONTINUATION_TIMEOUT,
                    total=DEFAULT_TOTAL_TIMEOUT)):
        """
        IP stack adapter

        Parameters
        ----------
        descriptor : str
            IP description
        port : int
            port used (optional, can be specified in descriptor)
        transport : Transport
            Transport protocol, TCP or UDP
        """
        super().__init__()
        self._transport = transport
        if transport == self.Protocol.TCP:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        elif transport == self.Protocol.UDP:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        else:
            raise ValueError("Invalid protocol")

        self._ip = descriptor # TODO : update this
        self._port = port
        self._stop_condition = stop_condition

    def set_default_port(self, port):
        """
        Sets IP port if no port has been set yet.

        This way, the user can leave the port empty
        and the driver/protocol can specify it later
        
        Parameters
        ----------
        port : int
        """
        if self._port is None:
            self._port = port        

    def open(self):
        self._socket.connect((self._ip, self._port))
        self._status = self.Status.CONNECTED

    def close(self):
        self._socket.close()
            
    def write(self, data : bytes):
        assert_byte_instance(data)
        if self._status == self.Status.DISCONNECTED:
            self.open()
        self._socket.send(data)

    def _read_thread(self, socket : socket.socket, read_queue : TimedQueue):
        while True:
            try:
                print(f"Wait for next...")
                byte = socket.recv(2)
            except OSError:
                break
            if not byte:
                break
            print(f"Put {byte} in queue")
            read_queue.put(byte)

    def _start_thread(self):
        self._thread = Thread(target=self._read_thread, daemon=True, args=(self._socket, self._read_queue))
        self._thread.start()

    def query(self, data : bytes):
        self.flushRead()
        self.write(data)
        return self.read()