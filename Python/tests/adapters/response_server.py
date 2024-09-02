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

from sys import argv
from argparse import ArgumentParser
import socket
from time import sleep
from enum import Enum
import select
import threading

HOST = 'localhost'
PORT = 8888

BUFFER_SIZE = 65_000

SEQUENCE_DELIMITER = b';'
DELAY_DELIMITER = b','

DISCONNECT = b'disconnect'

class Type(Enum):
    TCP = 'TCP'
    UDP = 'UDP'

def tcp_server():
    # Open the server
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((HOST, PORT)) # bind host address and port together
        s.listen()
        conn, _ = s.accept()  # accept new connection
        with conn:
            try:
                # We don't care about the data
                payload = conn.recv(BUFFER_SIZE)
            except socket.timeout:
                raise TimeoutError("Client didn't close or didn't send data")

            # Decrypt the payload
            sequences = payload_to_sequences(payload)

            # Send the sequence after the specified delay
            for s, t in sequences:
                sleep(t)
                if s == DISCONNECT:
                    conn.close()
                else:
                    conn.send(s)
                #break # Only send the first sequence as this is TCP

def udp_server():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((HOST, PORT))
        try:
            payload, addr = sock.recvfrom(BUFFER_SIZE) # buffer size is 1024 bytes
        except socket.timeout:
            raise TimeoutError("Client didn't close or didn't send data")
        # Send the sequence after the specified delay
        # Decrypt the payload
        sequences = payload_to_sequences(payload)

        for s, t in sequences:
            sleep(t)
            if s == DISCONNECT:
                sock.close()
                sock.detach()
            else:
                sock.sendto(s, addr)

def main():
    parser = ArgumentParser(
        prog='Response server',
        description='This script provides a TCP/UDP server that will respond with arbitrary data at specified delay'
    )
    parser.add_argument('-t', '--type', help='IP protocol : TCP or UDP', required=True, choices=[Type.TCP, Type.UDP])

    args = parser.parse_args()

    if args.type == Type.TCP:
        tcp_server()
    else:
        udp_server()

def payload_to_sequences(payload):
    # Split into sequences
    raw_sequences = [x.split(DELAY_DELIMITER) for x in payload.split(SEQUENCE_DELIMITER)]
    sequences = [(x[0], float(x[1])) for x in raw_sequences]
    return sequences

if __name__ == '__main__':
    main()


import threading

class StoppableThread(threading.Thread):
    """Thread class with a stop() method. The thread itself has to check
    regularly for the stopped() condition."""

    def __init__(self,  *args, **kwargs):
        super(StoppableThread, self).__init__(*args, **kwargs)
        self._stop_event = threading.Event()

    def stop(self):
        self._stop_event.set()

    def stopped(self):
        return self._stop_event.is_set()


# class ResponseServer():
#     def __init__(self, address : str, port : int, _type : Type) -> None:
#         self._address = address
#         self._port = port

#         _type = Type(_type)

#         self._stop_event = threading.Event()

#         if _type == Type.UDP:
#             raise NotImplementedError()
#         elif _type == Type.TCP:
#             self._thread = StoppableThread(target=self._tcp_server, args=(self._address, self._port, self._stop_event))
#             self._thread.start()

#     def stop(self):
#         if self._thread.is_alive():
#             self._stop_event.set()
#             self._thread.join()



#     def _tcp_server(self, address, port, stop_event : threading.Event):
#         print(f'Starting thread')
#             # Open the server
#         with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
#             s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
#             s.bind((address, port)) # bind host address and port together
#             s.listen()
#             conn, _ = s.accept()  # accept new connection
#             with conn:
#                 conn.setblocking(False)
#                 while True:
#                     try:
#                         # We don't care about the data
#                         print('Waiting for new data')
#                         payload = conn.recv(BUFFER_SIZE)
#                     except socket.timeout:
#                         raise TimeoutError("Client didn't close or didn't send data")
#                     print(f'Received : {payload}')

#                     # Decrypt the payload
#                     sequences = payload_to_sequences(payload)

#                     # Send the sequence after the specified delay
#                     for s, t in sequences:
#                         sleep(t)
#                         if s == DISCONNECT:
#                             print('Disconnecting server...')
#                             conn.close()
#                         else:
#                             conn.send(s)
#                         #break # Only send the first sequence as this is TCP
#                 print('Disconnecting...')