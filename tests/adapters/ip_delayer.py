# response_server.py
# Sébastien Deriaz
# 23.10.2023
#
#
# The goal of this script is to provide a TCP/UDP server that will respond with arbitrary data with specified delay
# The sequences and delays are specified by a client request
# Request format 
# TCP Server : ABCD,100
# UDP Server : ABCD,100;EFGH,200;IJKL,100;etc...
import socket
from time import sleep
from enum import Enum
import select
import threading
import logging

HOST = 'localhost'
PORT = 8888

BUFFER_SIZE = 65_000

SEQUENCE_DELIMITER = b';'
DELAY_DELIMITER = b','

DISCONNECT = b'disconnect'

class Type(Enum):
    TCP = 'TCP'
    UDP = 'UDP'


def payload_to_sequences(payload):
    # Split into sequences
    raw_sequences = [x.split(DELAY_DELIMITER) for x in payload.split(SEQUENCE_DELIMITER)]
    sequences = [(x[0], float(x[1])) for x in raw_sequences]
    return sequences


class StopLoop(Exception):
    pass

class IpDelayer():
    def __init__(self, address : str, port : int, _type : Type) -> None:
        self._address = address
        self._port = port
        self._logger = logging.getLogger('response_server')
        self._logger.info('Setting up response server')

        _type = Type(_type)

        self._thread_stop_read, self._thread_stop_write = socket.socketpair()

        if _type == Type.UDP:
            target = self._udp_server
        elif _type == Type.TCP:
            target = self._tcp_server
        self._thread = threading.Thread(target=target, args=(self._address, self._port, self._thread_stop_read))
        self._thread.start()

    def __del__(self):
        self.stop()

    def stop(self):
        self._logger.info('Closing server')
        if self._thread.is_alive():
            self._thread_stop_write.send(b'1')
            self._thread.join()

    def _udp_server(self, address, port, stop : socket.socket):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((HOST, PORT))
            try:
                while True:
                    try:
                        try:
                            ready, _, _ = select.select([sock, stop], [], [])
                        except ValueError:
                            # File descriptor is a negative number
                            raise StopLoop()
                        if stop in ready:
                            # Stop here
                            raise StopLoop()
                        else:
                            payload, addr = sock.recvfrom(BUFFER_SIZE) # buffer size is 1024 bytes
                    except socket.timeout:
                        raise TimeoutError("Client didn't close or didn't send data")
                    # Send the sequence after the specified delay
                    # Decrypt the payload
                    self._logger.debug(f'Parsing {payload}')
                    sequences = payload_to_sequences(payload)

                    for s, t in sequences:
                        self._logger.debug(f'Sending {s} after {t*1e3} ms')
                        sleep(t)
                        if s == DISCONNECT:
                            self._logger.debug('Closing UDP server')
                            raise StopLoop()
                        else:
                            sock.sendto(s, addr)
            except StopLoop:
                self._logger.debug('UDP server closed')


    def _tcp_server(self, address, port, stop : socket.socket):
            # Open the server
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((address, port)) # bind host address and port together
            s.listen(5)

            threads = []
            while True:
                ready, _, _ = select.select([s, stop], [], [])
                if stop in ready:
                    stop.recv(1)
                    # Stop all the client handles
                    thread : threading.Thread
                    for i, (stop_write, thread) in enumerate(threads):
                        #thread: threading.Thread
                        if thread.is_alive():
                            stop_write.send(b'1')
                            thread.join()
                    break
                else:
                    conn, _ = s.accept()
                    client_stop_read, client_stop_write = socket.socketpair()
                    threads.append((client_stop_write, threading.Thread(target=self.client_handle_thread, args=(conn, client_stop_read))))
                    threads[-1][1].start()

    def client_handle_thread(self, conn : socket.socket, stop : socket.socket):
        while True:
            try:
                ready, _, _ = select.select([conn, stop], [], [])
            except ValueError:
                # File descriptor is a negative number
                break
            else:
                if stop in ready:
                    # Stop the thread
                    stop.recv(1)
                    self._logger.info('Closing thread...')
                    conn.close()
                    break

                ready, _, _ = select.select([conn, stop], [], [])
                if stop in ready:
                    break
                
                payload = conn.recv(4096)

                if payload:
                    # Decrypt the payload
                    self._logger.debug(f'Parsing {payload}')
                    sequences = payload_to_sequences(payload)

                    # Send the sequence after the specified delay
                    for s, t in sequences:
                        self._logger.info(f'Sending {s} in {t*1e3} ms')
                        sleep(t)
                        if s == DISCONNECT:
                            conn.close()
                            break
                        else:
                            conn.send(s)
                        #break # Only send the first sequence as this is TCP
                else:
                    self._logger.info('Client disconnected')
                    break        
        