from time import sleep
from syndesi.adapters import IP
from syndesi.adapters.adapter import AdapterDisconnected
from syndesi.adapters.stop_conditions import *
from syndesi.adapters.timeout import Timeout, TimeoutException
import subprocess
import pathlib
import logging
server_file = pathlib.Path(__file__).parent / 'response_server.py'

from ip_delayer import IpDelayer

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
    server = IpDelayer(HOST, PORT, 'TCP')
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
    sleep(0.2)
    client.close()
    sleep(0.3)
    server.stop()


# Test response timeout
# not long enough to catch the first sequence
def test_response_B():
    server = IpDelayer(HOST, PORT, 'TCP')
    sleep(0.5)
    delay = 0.25
    sequence = b'ABCD'
    client = IP(
        HOST,
        port=PORT,
        stop_condition=None,
        timeout=Timeout(response=delay - TIME_DELTA, on_response='return'))
    client.write(encode_sequences([(sequence, delay)]))
    data = client.read()
    sleep(2*TIME_DELTA)
    assert data == b''
    logging.info('test')
    data = client.read()
    assert data == sequence
    server.stop()

# Test continuation timeout
# Long enough to catch the first two sequences

def test_continuation():
    server = IpDelayer(HOST, PORT, 'UDP')
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
    server.stop()

# Test transmission with big data over UDP
# The UDP buffer size is 
def test_too_big():
    server = IpDelayer(HOST, PORT, 'UDP')
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
    server.stop()

def test_length_valid():
    server = IpDelayer(HOST, PORT, 'UDP')
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
    server.stop()


# Test termination
def test_termination():
    server = IpDelayer(HOST, PORT, 'UDP')
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
    server.stop()

# Test termination with partial transmission of the termination
def test_termination_partial():
    server = IpDelayer(HOST, PORT, 'UDP')
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
    server.stop()

# Test length
def test_length():
    server = IpDelayer(HOST, PORT, 'TCP')
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
    server.stop()

# Test length with short timeout
def test_length_short_timeout():
    server = IpDelayer(HOST, PORT, 'TCP')
    sleep(0.5)
    sequence = b'ABCDEFGHIJKLMNOPQKRSTUVWXYZ'
    N = 10
    delay = 0.5
    client = IP(
        HOST,
        port=PORT,
        timeout=Timeout(response=delay - TIME_DELTA, on_response='return'),
        stop_condition=Length(10),
        )
    client.write(encode_sequences([(sequence, delay)]))
    data = client.read()
    assert data == b''
    client.close()
    server.stop()

# Test length with long timeout
def test_length_long_timeout():
    server = IpDelayer(HOST, PORT, 'TCP')
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
    server.stop()

# Test termination with long timeout
def test_termination_long_timeout():
    server = IpDelayer(HOST, PORT, 'UDP')
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
    server.stop()

# Test discard timeout (too short)
def test_discard_timeout_short():
    server = IpDelayer(HOST, PORT, 'UDP')
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
    server.stop()

# Test discard timeout (long enough)
def test_discard_timeout_long():
    server = IpDelayer(HOST, PORT, 'UDP')
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
    server.stop()


# Test return timeout (too short)
def test_return_timeout_short():
    server = IpDelayer(HOST, PORT, 'UDP')
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
    server.stop()

# Test return timeout (long enough)
def test_return_timeout_long():
    server = IpDelayer(HOST, PORT, 'UDP')
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
    server.stop()

# Test on_response=whatever except 'error'
def test_on_response_no_error():
    server = IpDelayer(HOST, PORT, 'UDP')
    for r in ['discard', 'return', 'store']:
        logging.debug(f'Testing {r}')
        sleep(0.2)
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
        del client
        sleep(1)
    server.stop()

# Test on_response='error'
def test_on_response_error():
    server = IpDelayer(HOST, PORT, 'UDP')
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
    server.stop()

# Test on_continuation='discard'
def test_continuation_discard():
    server = IpDelayer(HOST, PORT, 'UDP')
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
    server.stop()

# Test on_continuation='return'
def test_continuation_return():
    server = IpDelayer(HOST, PORT, 'UDP')
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
    server.stop()

# Test on_continuation='store'
def test_continuation_store():
    server = IpDelayer(HOST, PORT, 'UDP')
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
    server.stop()

# Test on_continuation='error'
def test_continuation_error():
    server = IpDelayer(HOST, PORT, 'UDP')
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
    server.stop()

# Test if a new configuration is correctly applied
def test_read_timeout_reconfiguration():
    server = IpDelayer(HOST, PORT, 'UDP')
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
    server.stop()

# Test if a new configuration is correctly applied
def test_disconnect():
    server = IpDelayer(HOST, PORT, 'TCP')
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
    except AdapterDisconnected as te:
        # Good !
        pass
    else:
        raise RuntimeError("No exception raised")
    client.close()
    server.stop()

def test_flush():
    server = IpDelayer(HOST, PORT, 'TCP')
    sleep(0.1)
    
    A = b'AAAAAAAA'
    B = b'XXXXXXXX'

    client = IP(
        HOST,
        port=PORT,
        timeout=Timeout(response=1, continuation=10e-3)
    )

    client.write(encode_sequences([(A, 0)]*3))
    sleep(1)
    client.flushRead()
    sleep(0.2)
    client.write(encode_sequences([(B, 0)]))
    data = client.read()
    assert data == B
    server.stop()