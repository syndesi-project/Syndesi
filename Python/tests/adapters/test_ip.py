from time import sleep
from syndesi.adapters import IP
from syndesi.adapters.stop_conditions import *
from syndesi.adapters.timeout import Timeout
import subprocess
import pathlib
server_file = pathlib.Path(__file__).parent / 'response_server.py'

HOST = 'localhost'
PORT = 8888

def encode_sequences(sequences : list):
    output = b''
    for i, (sequence, delay) in enumerate(sequences):
        if i > 0:
            output += b';'
        output += sequence + b',' + str(delay).encode('ASCII')
    return output

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
        timeout=delay + TIME_DELTA,
        stop_condition=None)
    client.write(encode_sequences([(sequence, delay)]))
    data = client.read()
    assert data == sequence
    client.close()

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
        timeout=delay - TIME_DELTA,
        stop_condition=None)
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
        timeout=Timeout(response=delay_response + TIME_DELTA, continuation=delay_continuation + TIME_DELTA),
        stop_condition=None,
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
        timeout=Timeout(response=delay + TIME_DELTA,
        continuation=TIME_DELTA),
        stop_condition=None,
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
        timeout=Timeout(response=delay + TIME_DELTA,
        continuation=TIME_DELTA),
        stop_condition=None,
        transport=IP.Protocol.UDP,
        buffer_size=len(sequence))
    client.write(encode_sequences([
        (sequence, delay)]))
    data = client.read()
    client.close()
    assert data == sequence


# Test termination
def test_termination():
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
        timeout=Timeout(response=delay+TIME_DELTA,continuation=delay+TIME_DELTA),
        stop_condition=Termination(termination),
        transport=IP.Protocol.UDP)
    client.write(encode_sequences([
        (sequence, delay)]))
    data = client.read()
    assert data == A
    data = client.read()
    assert data == B

# Test termination with partial transmission of the termination
def test_termination_partial():
    subprocess.Popen(['python', server_file, '-t', 'UDP'])
    sleep(0.5)
    delay = 0.25

    A = b'AAAA'
    B = b'BBBB'
    termination = b'XX'

    client = IP(
        HOST,
        port=PORT,
        timeout=Timeout(response=delay+TIME_DELTA,continuation=delay+TIME_DELTA),
        stop_condition=Termination(termination),
        transport=IP.Protocol.UDP)
    client.write(encode_sequences([
        (A + termination[:1], delay),
        (termination[1:] + B + termination, delay)]))
    data = client.read()
    assert data == A
    sleep(delay+TIME_DELTA)
    data = client.read()
    assert data == B

# Test length
def test_length():
    subprocess.Popen(['python', server_file, '-t', 'TCP'])
    sleep(0.5)
    sequence = b'ABCDEFGHIJKLMNOPQKRSTUVWXYZ'
    N = 10
    client = IP(
        HOST,
        port=PORT,
        stop_condition=Length(10)
        )
    client.write(encode_sequences([(sequence, 0)]))
    data = client.read()
    assert data == sequence[:10]
    data = client.read()
    assert data == sequence[10:20]
    client.close()

# Test length with short timeout
def test_length_short_timeout():
    subprocess.Popen(['python', server_file, '-t', 'TCP'])
    sleep(0.5)
    sequence = b'ABCDEFGHIJKLMNOPQKRSTUVWXYZ'
    N = 10
    delay = 0.5
    client = IP(
        HOST,
        port=PORT,
        timeout=Timeout(response=delay - TIME_DELTA),
        stop_condition=Length(10),
        )
    client.write(encode_sequences([(sequence, delay)]))
    data = client.read()
    assert data == b''
    client.close()

# Test length with long timeout
def test_length_long_timeout():
    subprocess.Popen(['python', server_file, '-t', 'TCP'])
    sleep(0.5)
    sequence = b'ABCDEFGHIJKLMNOPQKRSTUVWXYZ'
    N = 10
    delay = 0.5
    client = IP(
        HOST,
        port=PORT,
        timeout=Timeout(response=delay + TIME_DELTA, on_response='discard'),
        stop_condition=Length(10),
        )
    client.write(encode_sequences([(sequence, delay)]))
    data = client.read()
    assert data == sequence[:N]
    client.close()

# Test termination with long timeout
def test_termination_long_timeout():
    subprocess.Popen(['python', server_file, '-t', 'UDP'])
    sleep(0.5)
    A = b'ABCDEFGH'
    B = b'IJKLMNOPQKRSTUVWXYZ'
    termination = b'\n'
    delay = 0.5
    client = IP(
        HOST,
        port=PORT,
        timeout=Timeout(response=delay + TIME_DELTA, continuation=delay+TIME_DELTA),
        stop_condition=Termination(termination),
        transport=IP.Protocol.UDP
        )
    client.write(encode_sequences([(A, delay), (termination + B, delay)]))
    data = client.read()
    assert data == A
    client.close()

# Test discard timeout (too short)
def test_discard_timeout_short():
    subprocess.Popen(['python', server_file, '-t', 'UDP'])
    sleep(0.5)
    A = b'ABCDEFGH'
    B = b'IJKLMNOPQKRSTUVWXYZ'
    termination = b'\n'
    delay = 0.5
    client = IP(
        HOST,
        port=PORT,
        timeout=Timeout(response=delay + TIME_DELTA, continuation=delay-TIME_DELTA, on_continuation='discard'),
        stop_condition=Termination(termination),
        transport=IP.Protocol.UDP
        )
    client.write(encode_sequences([(A, delay), (termination + B, delay)]))
    data = client.read()
    assert data == b''
    client.close()

# Test discard timeout (long enough)
def test_discard_timeout_long():
    subprocess.Popen(['python', server_file, '-t', 'UDP'])
    sleep(0.5)
    A = b'ABCDEFGH'
    B = b'IJKLMNOPQKRSTUVWXYZ'
    termination = b'\n'
    delay = 0.5
    client = IP(
        HOST,
        port=PORT,
        timeout=Timeout(response=delay + TIME_DELTA, continuation=delay+TIME_DELTA, on_continuation='discard'),
        stop_condition=Termination(termination),
        transport=IP.Protocol.UDP
        )
    client.write(encode_sequences([(A, delay), (termination + B, delay)]))
    data = client.read()
    assert data == A
    client.close()


# Test return timeout (too short)
def test_return_timeout_short():
    subprocess.Popen(['python', server_file, '-t', 'UDP'])
    sleep(0.5)
    A = b'ABCDEFGH'
    B = b'IJKLMNOPQKRSTUVWXYZ'
    termination = b'\n'
    delay = 0.5
    client = IP(
        HOST,
        port=PORT,
        timeout=Timeout(response=delay + TIME_DELTA, continuation=delay-TIME_DELTA, on_continuation='return'),
        stop_condition=Termination(termination),
        transport=IP.Protocol.UDP
        )
    client.write(encode_sequences([(A, delay), (termination + B, delay)]))
    data = client.read()
    assert data == A
    client.close()

# Test return timeout (long enough)
def test_return_timeout_long():
    subprocess.Popen(['python', server_file, '-t', 'UDP'])
    sleep(0.5)
    A = b'ABCDEFGH'
    B = b'IJKLMNOPQKRSTUVWXYZ'
    termination = b'\n'
    delay = 0.5
    client = IP(
        HOST,
        port=PORT,
        timeout=Timeout(response=delay + TIME_DELTA, continuation=delay+TIME_DELTA, on_continuation='return'),
        stop_condition=Termination(termination),
        transport=IP.Protocol.UDP
        )
    client.write(encode_sequences([(A, delay), (termination + B, delay)]))
    data = client.read()
    assert data == A
    data = client.read()
    assert data == B
    client.close()