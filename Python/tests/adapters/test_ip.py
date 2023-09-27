import socket
from time import sleep
from threading import Thread
from syndesi.adapters import IP
from syndesi.adapters.stop_conditions import *

HOST = 'localhost'
PORT = 8888

def server_thread():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # look closely. The bind() function takes tuple as argument
    s.bind((HOST, PORT)) # bind host address and port together

    # configure how many client the server can listen simultaneously
    s.listen()
    conn, _ = s.accept()  # accept new connection
    with conn:
        while True:
            # receive data stream. it won't accept data packet greater than 1024 bytes
            try:
                data = conn.recv(1024)
            except socket.TimeoutError:
                raise TimeoutError("Client didn't close or didn't send data")
            if not data:
                break

            # Simulate a TCP exchange in multiple parts
            # Don't know if this is the correct way of doing things
            for t, s in SEQUENCES:
                sleep(t)
                try:
                    conn.send(s)
                except (BrokenPipeError, ConnectionResetError):
                    break
    conn.close()  # close the connection

# Send each sequence [1] after [0] time
SEQUENCES = [
    (0.25, b'ABCDE'),
    (0.1, b'FGHIJ'),
    (0.5, b'KLMNO'),
    (1, b'PQRST'),
    (1, b'UVWXYZ')
]
TIME_DELTA = 1e-3
CLIENT_SEQUENCE = b'ABCDE'
TIME_PER_BYTE = 0.1

# Test response timeout
# long enough to catch the first sequence

def test_response_A():
    thread = Thread(target=server_thread, daemon=True)
    thread.start()
    # This should catch the first sequence
    sleep(0.1)
    client = IP(
        HOST,
        port=PORT,
        stop_condition=Timeout(response=SEQUENCES[0][0] + TIME_DELTA,
        continuation=0.01))
    client.write(CLIENT_SEQUENCE)
    data = client.read()
    client.close()
    assert data == SEQUENCES[0][1]
    thread.join()

# Test response timeout
# not long enough to catch the first sequence

def test_response_B():
    thread = Thread(target=server_thread, daemon=True)
    thread.start()
    # This sould not    
    sleep(0.1)
    client = IP(
        HOST,
        port=PORT,
        stop_condition=Timeout(response=SEQUENCES[0][0] - TIME_DELTA,
        continuation=0.01))
    client.write(CLIENT_SEQUENCE)
    data = client.read()
    client.close()
    assert data == b''
    thread.join()

# Test continuation timeout
# Long enough to catch the first two sequences

def test_continuation():
    thread = Thread(target=server_thread, daemon=True)
    thread.start()
    # This sould not    
    sleep(0.1)
    client = IP(
        HOST,
        port=PORT,
        stop_condition=Timeout(response=SEQUENCES[0][0] + TIME_DELTA,
        continuation=SEQUENCES[1][0] + TIME_DELTA))
    client.write(CLIENT_SEQUENCE)
    data = client.read()
    client.close()
    assert data == SEQUENCES[0][1] + SEQUENCES[1][1]
    thread.join()

# Test total timeout
# This should be long enough to catch the first three sequences

def test_total_A():
    thread = Thread(target=server_thread, daemon=True)
    thread.start()
    # This sould not    
    sleep(0.1)
    client = IP(
        HOST,
        port=PORT,
        stop_condition=Timeout(response=SEQUENCES[0][0] + TIME_DELTA,
            continuation=10,
            #total=sum(s[0] + TIME_DELTA for s in SEQUENCES[:3]))
            total=sum(s[0] + TIME_DELTA for s in SEQUENCES[:3])
        )
        )
    client.write(CLIENT_SEQUENCE)
    data = client.read()
    client.close()
    assert data == b''.join(s[1] for s in SEQUENCES[:3])
    thread.join()

# Test termination
def test_termination_A():
    thread = Thread(target=server_thread, daemon=True)
    thread.start()
    # This sould not
    sleep(0.1)
    client = IP(
        HOST,
        port=PORT,
        stop_condition=Termination(b'F')
        )
    client.write(CLIENT_SEQUENCE)
    data = client.read()
    client.close()
    complete_sequence = b''.join(s[1] for s in SEQUENCES)
    assert data == complete_sequence[:complete_sequence.index(b'F')+1]
    thread.join()


# Test length
def test_length():
    thread = Thread(target=server_thread, daemon=True)
    thread.start()
    # This sould not
    sleep(0.1)
    client = IP(
        HOST,
        port=PORT,
        stop_condition=Length(10)
        )
    client.write(CLIENT_SEQUENCE)
    data = client.read()
    client.close()
    complete_sequence = b''.join(s[1] for s in SEQUENCES)
    assert data == complete_sequence[:10]
    thread.join()

