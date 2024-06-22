# remote_server.py
# Sébastien Deriaz
# 28.05.2024
import argparse
from enum import Enum
from ..adapters import SerialPort
from ..adapters.adapter import AdapterDisconnected
from ..adapters.remote import DEFAULT_PORT
from ..adapters.ip_server import IPServer
from typing import Union
from .remote_api import *
import logging
from .log import LoggerAlias, set_log_stream

class AdapterType(Enum):
    SERIAL = 'serial'
    IP = 'ip'

DEFAULT_BAUDRATE = 115200

def main():
    parser = argparse.ArgumentParser(
        prog='syndesi-remote',
        description='Syndesi remote server',
        epilog='')
    # Parse subcommand
    parser.add_argument('-t', '--adapter_type', choices=[x.value for x in AdapterType], default=AdapterType.IP)
    parser.add_argument('-p', '--port', type=int, default=DEFAULT_PORT, help='IP port')
    parser.add_argument('-a', '--address', default=None, type=str, help='IP address or serial port')
    parser.add_argument('-b', '--baudrate', type=int, default=DEFAULT_BAUDRATE, help='Serial baudrate')
    parser.add_argument('-v', '--verbose', action='store_true')

    args = parser.parse_args()

    if args.verbose:
        set_log_stream(True, 'DEBUG')

    remote_server = RemoteServer(adapter_type=args.adapter_type, port=args.port, address=args.address, baudrate=args.baudrate)

    remote_server.start()

class RemoteServer:
    def __init__(self, adapter_type : AdapterType, port : Union[str, int], address : str, baudrate : int) -> None:
        self._adapter_type = AdapterType(adapter_type)
        self._adapter = None
        self._port = port
        self._address = address
        self._baudrate = baudrate
        self._logger = logging.getLogger(LoggerAlias.REMOTE_SERVER.value)
        self._logger.info('Initializing remote server')

    def start(self):
        self._logger.info(f"Starting remote server with {self._adapter_type.value} adapter")
        
        if self._adapter_type == AdapterType.SERIAL:
            # If adapter type is serial, create the adapter directly
            self._master_adapter = SerialPort(self._address, baudrate=self._baudrate)
        elif self._adapter_type == AdapterType.IP:
            # Otherwise, create a server to get IP clients
            server = IPServer(port=self._port, transport='TCP', address=self._address, max_clients=1, stop_condition=None)
            server.open()


        # If the adapter type is IP, use the external while loop to get clients
        while True:
            print("Waiting for client...")
            self._master_adapter = server.get_client()
            print("Client connected")

            while True:
                try:
                    call_raw = self._master_adapter.read()
                except AdapterDisconnected:
                    print(f"Client disconnected")
                    break

                api_call = parse(call_raw)

                self._logger.debug(f'Received {type(api_call)}')

                output = self.manage_call(api_call)

                self._master_adapter.write(output.encode())

                if self._adapter_type == AdapterType.IP:
                    if not self._master_adapter.read_thread_alive():
                        print("Read thread is dead, breaking read loop")
                        break



            # Loop only if we need to get a new client
            if self._adapter_type != AdapterType.IP:
                break

        

    def manage_call(self, c : APICall) -> APICall:
        output = None
        if isinstance(c, IPAdapterInstanciate):
            self._adapter = IP(
                address=c.address,
                port=c.port)
            output = ReturnStatus(True)
        elif isinstance(c, AdapterOpen):
            if self._adapter is None:
                output = ReturnStatus(False, 'Cannot open uninstanciated adapter')
            self._adapter.open()
            output = ReturnStatus(True)
        elif isinstance(c, AdapterClose):
            if self._adapter is None:
                output = ReturnStatus(False, 'Cannot close uninstanciated adapter')
            else:
                self._adapter.close()
                output = ReturnStatus(True)
        elif isinstance(c, AdapterWrite):
            if self._adapter is None:
                output = ReturnStatus(False, 'Cannot write to uninstanciated adapter')
            else:
                self._adapter.write(c.data)
                output = ReturnStatus(True)
        elif isinstance(c, AdapterFlushRead):
            self._adapter.flushRead()
            output = ReturnStatus(True)
        elif isinstance(c, AdapterRead):
            # TODO : Implement return_metrics
            data = self._adapter.read()
            output = AdapterReadReturn(data=data)

        return output

if __name__ == '__main__':
    main()