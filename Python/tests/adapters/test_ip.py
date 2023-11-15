from time import sleep
from syndesi.adapters import IP
from syndesi.adapters.stop_conditions import *
import subprocess
import pathlib
server_file = pathlib.Path(__file__).parent / 'response_server.py'

HOST = 'localhost'
PORT = 8888

#server_process = subprocess.run(['python', 'response_server.py', '-t', 'TCP'])

def encode_sequences(sequences : list):
    output = b''
    for i, (sequence, delay) in enumerate(sequences):
        if i > 0:
            output += b';'
        output += sequence + b',' + str(delay).encode('ASCII')
    return output

# Send each sequence [1] after [0] time

TIME_DELTA = 5e-3

# Test response timeout
# long enough to catch the first sequence

def test_response_A():
    subprocess.Popen(['python', server_file, '-t', 'TCP'])
    sleep(0.5)
    # This should catch the first sequence
    delay = 0.25
    sequence = b'ABCD'
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

# Test response timeout
# not long enough to catch the first sequence

def test_response_B():
    subprocess.Popen(['python', server_file, '-t', 'TCP'])
    sleep(0.5)
    delay = 0.25
    sequence = b'ABCD'
    client = IP(
        HOST,
        port=PORT,
        stop_condition=Timeout(response=delay - TIME_DELTA,
        continuation=0.01))
    client.write(encode_sequences([(sequence, delay)]))
    data = client.read()
    sleep(2*TIME_DELTA)
    assert data == b''
    data = client.read()
    assert data == sequence

# Test continuation timeout
# Long enough to catch the first two sequences

def test_continuation():
    subprocess.Popen(['python', server_file, '-t', 'UDP'])
    sleep(0.5)
    delay_response = 0.25
    sequence_response = b'ABCDE'
    delay_continuation = 0.3
    sequence_continuation = b'FGHIJKL'

    client = IP(
        HOST,
        port=PORT,
        stop_condition=Timeout(response=delay_response + TIME_DELTA,
        continuation=delay_continuation + TIME_DELTA),
        transport=IP.Protocol.UDP)
    client.write(encode_sequences([
        (sequence_response, delay_response),
        (sequence_continuation, delay_continuation)]))
    data = client.read()
    client.close()
    assert data == sequence_response + sequence_continuation

# Test transmission with big data over UDP
# The UDP buffer size is 
def test_too_big():
    subprocess.Popen(['python', server_file, '-t', 'UDP'])
    sleep(0.5)
    delay = 0.25
    sequence = 2000*b'A'

    client = IP(
        HOST,
        port=PORT,
        stop_condition=Timeout(response=delay + TIME_DELTA,
        continuation=TIME_DELTA),
        transport=IP.Protocol.UDP)
    client.write(encode_sequences([
        (sequence, delay)]))
    data = client.read()
    client.close()
    assert data != sequence

def test_length_valid():
    subprocess.Popen(['python', server_file, '-t', 'UDP'])
    sleep(0.5)
    delay = 0.25
    sequence = 2000*b'A'

    client = IP(
        HOST,
        port=PORT,
        stop_condition=Timeout(response=delay + TIME_DELTA,
        continuation=TIME_DELTA),
        transport=IP.Protocol.UDP,
        buffer_size=len(sequence))
    client.write(encode_sequences([
        (sequence, delay)]))
    data = client.read()
    client.close()
    assert data == sequence


# Test termination
def test_termination_A():
    subprocess.Popen(['python', server_file, '-t', 'UDP'])
    sleep(0.5)
    delay = 0.25
    A = b'AAAA'
    B = b'BBBB'
    termination = b'X'
    sequence = A + termination + B + termination

    client = IP(
        HOST,
        port=PORT,
        stop_condition=Termination(b'X'),
        transport=IP.Protocol.UDP,
        buffer_size=len(sequence))
    client.write(encode_sequences([
        (sequence, delay)]))
    data = client.read()
    assert data == A
    data = client.read()
    assert data == B


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

