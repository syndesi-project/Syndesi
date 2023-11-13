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

HOST = 'localhost'
PORT = 8888

SEQUENCE_DELIMITER = b';'
DELAY_DELIMITER = b','

class Types:
    TCP = 'TCP'
    UDP = 'UDP'

def tcp_server():
    # Open the server
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind((HOST, PORT)) # bind host address and port together

    s.listen()
    conn, _ = s.accept()  # accept new connection
    with conn:
        try:
            # We don't care about the data
            payload = conn.recv(1024)
        except socket.timeout:
            raise TimeoutError("Client didn't close or didn't send data")

        print(f"Payload : {payload}")
        # Decrypt the payload
        sequences = payload_to_sequences(payload)

        # Send the sequence after the specified delay
        for s, t in sequences:
            print(f"Wait {t}s...")
            sleep(t)
            print(f"Send {s}")
            conn.send(s)
            break # Only send the first sequence as this is TCP
        print("End connection")
    #conn.close()  # close the connection

def udp_server():
    sock = socket.socket(socket.AF_INET, # Internet
                        socket.SOCK_DGRAM) # UDP
    sock.bind((HOST, PORT))
   
    while True:
        try:
            payload = sock.recvfrom(1024) # buffer size is 1024 bytes
        except socket.timeout:
            raise TimeoutError("Client didn't close or didn't send data")
        # Send the sequence after the specified delay
        print(f"Payload : {payload}")
        # Decrypt the payload
        sequences = payload_to_sequences(payload)

        for t, s in sequences:
            sleep(t)
            sock.send(s)

def main():
    parser = ArgumentParser(
        prog='Response server',
        description='This script provides a TCP/UDP server that will respond with arbitrary data at specified delay'
    )
    parser.add_argument('-t', '--type', help='IP protocol : TCP or UDP', required=True, choices=[Types.TCP, Types.UDP])

    args = parser.parse_args()

    if args.type == Types.TCP:
        print("Starting TCP server...")
        tcp_server()
    else:
        print("Starting UDP server...")
        udp_server()

def payload_to_sequences(payload): 
    # Split into sequences
    raw_sequences = [x.split(DELAY_DELIMITER) for x in payload.split(SEQUENCE_DELIMITER)]
    sequences = [(x[0], float(x[1])) for x in raw_sequences]
    print(f"Sequences : {sequences}")
    return sequences

if __name__ == '__main__':
    main()