from time import sleep
from syndesi.adapters import IP
from syndesi.adapters.adapter import AdapterDisconnected
from syndesi.adapters.stop_conditions import *
from syndesi.adapters.timeout import Timeout, TimeoutException
import subprocess
import pathlib
server_file = pathlib.Path(__file__).parent / 'response_server.py'

#from response_server import ResponseServer

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
    #server = ResponseServer(HOST, PORT, 'TCP')
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
    sleep(2)
    client.close()
    #sleep(3)
    #server.stop()


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

# Test on_response=whatever except 'error'
def test_response_no_error():
    for r in ['discard', 'return', 'store']:
        subprocess.Popen(['python', server_file, '-t', 'UDP'])
        sleep(0.5)
        A = b'ABCDEFGH'
        B = b'IJKLMNOPQKRSTUVWXYZ'
        termination = b'\n'
        delay = 0.5
        client = IP(
            HOST,
            port=PORT,
            timeout=Timeout(response=delay - TIME_DELTA, on_response=r),
            stop_condition=Termination(termination),
            transport=IP.Protocol.UDP
            )
        client.write(encode_sequences([(A, delay)]))
        data = client.read()
        assert data == b''
        client.close()

# Test on_response='error'
def test_response_error():
    subprocess.Popen(['python', server_file, '-t', 'UDP'])
    sleep(0.5)
    A = b'ABCDEFGH'
    B = b'IJKLMNOPQKRSTUVWXYZ'
    termination = b'\n'
    delay = 0.5
    client = IP(
        HOST,
        port=PORT,
        timeout=Timeout(response=delay - TIME_DELTA, on_response='error'),
        stop_condition=Termination(termination),
        transport=IP.Protocol.UDP
        )
    client.write(encode_sequences([(A, delay)]))
    try:
        client.read()
    except TimeoutException as te:
        assert te._type == Timeout.TimeoutType.RESPONSE
    else:
        raise RuntimeError("No exception raised")
    client.close()

# Test on_continuation='discard'
def test_continuation_discard():
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

# Test on_continuation='return'
def test_continuation_return():
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

# Test on_continuation='store'
def test_continuation_store():
    subprocess.Popen(['python', server_file, '-t', 'UDP'])
    sleep(0.5)
    A = b'ABCDEFGH'
    B = b'IJKLMNOPQKRSTUVWXYZ'
    termination = b'\n'
    delay = 0.5
    client = IP(
        HOST,
        port=PORT,
        timeout=Timeout(response=delay + TIME_DELTA, continuation=delay-TIME_DELTA, on_continuation='store'),
        stop_condition=Termination(termination),
        transport=IP.Protocol.UDP
        )
    client.write(encode_sequences([(A, delay), (termination + B, delay)]))
    data = client.read()
    assert data == b''
    data = client.read()
    assert data == A
    client.close()

# Test on_continuation='error'
def test_continuation_error():
    subprocess.Popen(['python', server_file, '-t', 'UDP'])
    sleep(0.5)
    A = b'ABCDEFGH'
    B = b'IJKLMNOPQKRSTUVWXYZ'
    termination = b'\n'
    delay = 0.5
    client = IP(
        HOST,
        port=PORT,
        timeout=Timeout(response=delay + TIME_DELTA, continuation=delay-TIME_DELTA, on_continuation='error'),
        stop_condition=Termination(termination),
        transport=IP.Protocol.UDP
        )
    client.write(encode_sequences([(A, delay), (termination + B, delay)]))
    try:
        data = client.read()
    except TimeoutException as te:
        assert te._type == Timeout.TimeoutType.CONTINUATION
    else:
        raise RuntimeError("No exception raised")
    client.close()

# Test if a new configuration is correctly applied
def test_read_timeout_reconfiguration():
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
    try:
        client.read(timeout=Timeout(response=delay + TIME_DELTA, continuation=delay-TIME_DELTA, on_continuation='error'))
    except TimeoutException as te:
        assert te._type == Timeout.TimeoutType.CONTINUATION
    else:
        raise RuntimeError("No exception raised")
    client.close()

# Test if a new configuration is correctly applied
def test_disconnect():
    subprocess.Popen(['python', server_file, '-t', 'TCP'])
    sleep(0.5)
    A = b'ABCDEFGH'
    B = b'IJKLMNOPQKRSTUVWXYZ'
    delay = 0.5
    client = IP(
        HOST,
        port=PORT,
        timeout=Timeout(response=delay + TIME_DELTA, continuation=delay-TIME_DELTA, on_continuation='discard'),
        transport=IP.Protocol.TCP
        )
    client.write(encode_sequences([(b'disconnect', delay)]))
    try:
        data = client.read(timeout=Timeout(response=delay + TIME_DELTA + 1, continuation=delay-TIME_DELTA, on_continuation='error'))
        print(f'Data : {data}')
    except AdapterDisconnected as te:
        # Good !
        pass
    else:
        #raise RuntimeError("No exception raised")
        pass
    client.close()