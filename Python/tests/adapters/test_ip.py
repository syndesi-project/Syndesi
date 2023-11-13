from time import sleep
from syndesi.adapters import IP
from syndesi.adapters.stop_conditions import *
import subprocess

HOST = 'localhost'
PORT = 8888

SEQUENCE = [
    (0.25, b'ABCDE'),
    (0.1, b'FGHIJ'),
    (0.5, b'KLMNO'),
    (1, b'PQRST'),
    (1, b'UVWXYZ')
]

#server_process = subprocess.run(['python', 'response_server.py', '-t', 'TCP'])

def encode_sequences(sequences : list):
    output = b''
    for sequence, delay in sequences:
        output += f"{sequence},{delay}".encode('ASCII')
    return output

# Send each sequence [1] after [0] time

TIME_DELTA = 1e-3

# Test response timeout
# long enough to catch the first sequence

def test_response_A():
    # This should catch the first sequence
    sleep(0.1)
    delay = 0.25
    sequence = 'ABCD'
    client = IP(
        HOST,
        port=PORT,
        stop_condition=Timeout(response=delay + TIME_DELTA + 1,
        continuation=0.01))
    client.write(encode_sequences([(sequence, delay)]))
    data = client.read()
    print(f"Data : {data}")
    client.close()
    assert data == sequence

# # Test response timeout
# # not long enough to catch the first sequence

# def test_response_B():
#     sleep(0.1)
#     delay = 0.25
#     sequence = 'ABCD'
#     client = IP(
#         HOST,
#         port=PORT,
#         stop_condition=Timeout(response=delay - TIME_DELTA,
#         continuation=0.01))
#     client.write(f"{sequence},{delay}")
#     data = client.read()
#     client.close()
#     assert data == b''

# # Test continuation timeout
# # Long enough to catch the first two sequences

# def test_continuation():
#     sleep(0.1)
#     delay = 0.25
#     sequence = 'ABCDE'

#     client = IP(
#         HOST,
#         port=PORT,
#         stop_condition=Timeout(response=delay + TIME_DELTA,
#         continuation=SEQUENCE[1][0] + TIME_DELTA))
#     client.write(f"{sequence},{delay}")
#     data = client.read()
#     client.close()
#     #assert data == SEQUENCE[0][1] + SEQUENCE[1][1]

# # Test total timeout
# # This should be long enough to catch the first three sequences

# def test_total_A():
#     sleep(0.1)
#     delay = 0.25
#     sequence = 'ABCDE'
#     client = IP(
#         HOST,
#         port=PORT,
#         stop_condition=Timeout(response=delay + TIME_DELTA,
#             continuation=10,
#             #total=sum(s[0] + TIME_DELTA for s in SEQUENCES[:3]))
#             total=sum(s[0] + TIME_DELTA for s in SEQUENCE[:3])
#         )
#         )
#     client.write(f"{sequence},{delay}")
#     data = client.read()
#     client.close()
#     #assert data == b''.join(s[1] for s in SEQUENCE[:3])

# # Test termination
# def test_termination_A():
#     sleep(0.1)
#     client = IP(
#         HOST,
#         port=PORT,
#         stop_condition=Termination(b'F')
#         )
#     client.write(CLIENT_SEQUENCE)
#     data = client.read()
#     client.close()
#     #complete_sequence = b''.join(s[1] for s in SEQUENCE)
#     #assert data == complete_sequence[:complete_sequence.index(b'F')+1]


# # Test length
# def test_length():    
#     sleep(0.1)
#     client = IP(
#         HOST,
#         port=PORT,
#         stop_condition=Length(10)
#         )
#     client.write(CLIENT_SEQUENCE)
#     data = client.read()
#     client.close()
#     #complete_sequence = b''.join(s[1] for s in SEQUENCE)
#     #assert data == complete_sequence[:10]

