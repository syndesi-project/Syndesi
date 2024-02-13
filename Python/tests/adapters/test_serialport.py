from time import sleep
from syndesi.adapters import SerialPort
from syndesi.adapters.stop_conditions import *
from syndesi.adapters.timeout import Timeout, TimeoutException

PORT = '/dev/ttyACM1'
BAUDRATE = 115200

OPEN_DELAY = 2

def encode_sequences(sequences : list):
    output = b''
    for i, (sequence, delay) in enumerate(sequences):
        if i > 0:
            output += b';'
        output += sequence + b',' + f'{delay*1e3:.0f}'.encode('ASCII')
    output += b'\n'
    return output

TIME_DELTA = 10e-3

# Test response timeout
# long enough to catch the first sequence
def test_response_A():
    # This should catch the first sequence
    delay = 0.25
    sequence = b'ABCD'
    client = SerialPort(
        port=PORT,
        baudrate=BAUDRATE,
        timeout=delay + TIME_DELTA,
        stop_condition=None)
    sleep(OPEN_DELAY)
    client.write(encode_sequences([(sequence, delay)]))
    data = client.read()
    assert data == sequence
    client.close()

# Test response timeout
# not long enough to catch the first sequence

def test_response_B():
    delay = 0.25
    sequence = b'ABCD'
    client = SerialPort(
        port=PORT,
        baudrate=BAUDRATE,
        timeout=delay - TIME_DELTA,
        stop_condition=None)
    sleep(OPEN_DELAY)
    client.write(encode_sequences([(sequence, delay)]))
    data = client.read()
    sleep(2*TIME_DELTA)
    assert data == b''
    data = client.read()
    client.close()
    assert data == sequence

# Test continuation timeout
# Long enough to catch the first two sequences
def test_continuation():
    
    delay_response = 0.25
    sequence_response = b'ABCDE'
    delay_continuation = 0.5
    sequence_continuation = b'FGHIJKL'

    client = SerialPort(
        port=PORT,
        baudrate=BAUDRATE,
        timeout=Timeout(response=delay_response + TIME_DELTA, continuation=delay_continuation + TIME_DELTA, on_response='error'),
        stop_condition=None)
    sleep(OPEN_DELAY)
    client.write(encode_sequences([
        (sequence_response, delay_response),
        (sequence_continuation, delay_continuation)]))
    data = client.read()
    client.close()
    assert data == sequence_response + sequence_continuation
 
def test_big():
    delay = 0.25
    sequence = 1000*b'A'

    client = SerialPort(
        port=PORT,
        baudrate=BAUDRATE,
        timeout=Timeout(response=delay + TIME_DELTA,
        continuation=TIME_DELTA),
        stop_condition=None)
    sleep(OPEN_DELAY)
    client.write(encode_sequences([
        (sequence, delay)]))
    data = client.read()
    client.close()
    assert data == sequence


# Test termination
def test_termination():
    delay = 0.25
    A = b'AAAA'
    B = b'BBBB'
    termination = b'X'
    sequence = A + termination + B + termination

    client = SerialPort(
        port=PORT,
        baudrate=BAUDRATE,
        timeout=Timeout(response=delay+TIME_DELTA,continuation=delay+TIME_DELTA),
        stop_condition=Termination(termination))
    sleep(OPEN_DELAY)
    client.write(encode_sequences([
        (sequence, delay)]))
    data = client.read()
    assert data == A
    data = client.read()
    client.close()
    assert data == B

# Test termination with partial transmission of the termination
def test_termination_partial():
    delay = 0.25

    A = b'AAAA'
    B = b'BBBB'
    termination = b'XX'

    client = SerialPort(
        port=PORT,
        baudrate=BAUDRATE,
        timeout=Timeout(response=delay+TIME_DELTA,continuation=delay+TIME_DELTA),
        stop_condition=Termination(termination))
    sleep(OPEN_DELAY)
    client.write(encode_sequences([
        (A + termination[:1], delay),
        (termination[1:] + B + termination, delay)]))
    data = client.read()
    assert data == A
    sleep(delay+TIME_DELTA)
    data = client.read()
    client.close()
    assert data == B

# Test length
def test_length():
    sequence = b'ABCDEFGHIJKLMNOPQKRSTUVWXYZ'
    N = 10
    client = SerialPort(
        port=PORT,
        baudrate=BAUDRATE,
        stop_condition=Length(10)
        )
    sleep(OPEN_DELAY)
    client.write(encode_sequences([(sequence, 0)]))
    data = client.read()
    assert data == sequence[:10]
    data = client.read()
    assert data == sequence[10:20]
    client.close()

# Test length with short timeout
def test_length_short_timeout():
    sequence = b'ABCDEFGHIJKLMNOPQKRSTUVWXYZ'
    N = 10
    delay = 0.5
    client = SerialPort(
        port=PORT,
        baudrate=BAUDRATE,
        timeout=Timeout(response=delay - TIME_DELTA),
        stop_condition=Length(10),
        )
    sleep(OPEN_DELAY)
    client.write(encode_sequences([(sequence, delay)]))
    data = client.read()
    assert data == b''
    client.close()

# Test length with long timeout
def test_length_long_timeout():
    sequence = b'ABCDEFGHIJKLMNOPQKRSTUVWXYZ'
    N = 10
    delay = 0.5
    client = SerialPort(
        port=PORT,
        baudrate=BAUDRATE,
        timeout=Timeout(response=delay + TIME_DELTA, on_response='discard'),
        stop_condition=Length(10),
        )
    sleep(OPEN_DELAY)
    client.write(encode_sequences([(sequence, delay)]))
    data = client.read()
    assert data == sequence[:N]
    #client.close()

# Test termination with long timeout
def test_termination_long_timeout():
    A = b'ABCDEFGH'
    B = b'IJKLMNOPQKRSTUVWXYZ'
    termination = b'*'
    delay = 0.5
    client = SerialPort(
        port=PORT,
        baudrate=BAUDRATE,
        timeout=Timeout(response=delay + TIME_DELTA, continuation=delay+TIME_DELTA),
        stop_condition=Termination(termination)
        )
    sleep(OPEN_DELAY)
    client.write(encode_sequences([(A, delay), (termination + B, delay)]))
    data = client.read()
    assert data == A
    client.close()

# Test discard timeout (too short)
def test_discard_timeout_short():
    A = b'ABCDEFGH'
    B = b'IJKLMNOPQKRSTUVWXYZ'
    termination = b'*'
    delay = 0.5
    client = SerialPort(
        port=PORT,
        baudrate=BAUDRATE,
        timeout=Timeout(response=delay + TIME_DELTA, continuation=delay-TIME_DELTA, on_continuation='discard'),
        stop_condition=Termination(termination)
        )
    sleep(OPEN_DELAY)
    client.write(encode_sequences([(A, delay), (termination + B, delay)]))
    data = client.read()
    assert data == b''
    #client.close()

# Test discard timeout (long enough)
def test_discard_timeout_long():
    A = b'ABCDEFGH'
    B = b'IJKLMNOPQKRSTUVWXYZ'
    termination = b'*'
    delay = 0.5
    client = SerialPort(
        port=PORT,
        baudrate=BAUDRATE,
        timeout=Timeout(response=delay + TIME_DELTA, continuation=delay+TIME_DELTA, on_continuation='discard'),
        stop_condition=Termination(termination)
        )
    sleep(OPEN_DELAY)
    client.write(encode_sequences([(A, delay), (termination + B, delay)]))
    data = client.read()
    assert data == A
    client.close()


# Test return timeout (too short)
def test_return_timeout_short():
    A = b'ABCDEFGH'
    B = b'IJKLMNOPQKRSTUVWXYZ'
    termination = b'*'
    delay = 0.5
    client = SerialPort(
        port=PORT,
        baudrate=BAUDRATE,
        timeout=Timeout(response=delay + TIME_DELTA, continuation=delay-TIME_DELTA, on_continuation='return'),
        stop_condition=Termination(termination)
        )
    sleep(OPEN_DELAY)
    client.write(encode_sequences([(A, delay), (termination + B, delay)]))
    data = client.read()
    assert data == A
    client.close()

# Test return timeout (long enough)
def test_return_timeout_long():
    A = b'ABCDEFGH'
    B = b'IJKLMNOPQKRSTUVWXYZ'
    termination = b'*'
    delay = 0.5
    client = SerialPort(
        port=PORT,
        baudrate=BAUDRATE,
        timeout=Timeout(response=delay + TIME_DELTA, continuation=delay+TIME_DELTA, on_continuation='return'),
        stop_condition=Termination(termination)
        )
    sleep(OPEN_DELAY)
    client.write(encode_sequences([(A, delay), (termination + B, delay)]))
    data = client.read()
    assert data == A
    data = client.read()
    assert data == B
    client.close()

# Test on_response=whatever except 'error'
def test_response_no_error():
    for r in ['discard', 'return', 'store']:
        A = b'ABCDEFGH'
        B = b'IJKLMNOPQKRSTUVWXYZ'
        termination = b'*'
        delay = 0.5
        client = SerialPort(
            port=PORT,
            baudrate=BAUDRATE,
            timeout=Timeout(response=delay - TIME_DELTA, on_response=r),
            stop_condition=Termination(termination)
            )
        sleep(OPEN_DELAY)
        client.write(encode_sequences([(A, delay)]))
        data = client.read()
        assert data == b''
        client.close()

# Test on_response='error'
def test_response_error():
    A = b'ABCDEFGH'
    B = b'IJKLMNOPQKRSTUVWXYZ'
    termination = b'*'
    delay = 0.5
    client = SerialPort(
        port=PORT,
        baudrate=BAUDRATE,
        timeout=Timeout(response=delay - TIME_DELTA, on_response='error'),
        stop_condition=Termination(termination),
        )
    sleep(OPEN_DELAY)
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
    A = b'ABCDEFGH'
    B = b'IJKLMNOPQKRSTUVWXYZ'
    termination = b'*'
    delay = 0.5
    client = SerialPort(
        port=PORT,
        baudrate=BAUDRATE,
        timeout=Timeout(response=delay + TIME_DELTA, continuation=delay-TIME_DELTA, on_continuation='discard'),
        stop_condition=Termination(termination)
        )
    sleep(OPEN_DELAY)
    client.write(encode_sequences([(A, delay), (termination + B, delay)]))
    data = client.read()
    assert data == b''
    client.close()

# Test on_continuation='return'
def test_continuation_return():
    A = b'ABCDEFGH'
    B = b'IJKLMNOPQKRSTUVWXYZ'
    termination = b'*'
    delay = 0.5
    client = SerialPort(
        port=PORT,
        baudrate=BAUDRATE,
        timeout=Timeout(response=delay + TIME_DELTA, continuation=delay-TIME_DELTA, on_continuation='return'),
        stop_condition=Termination(termination)
        )
    sleep(OPEN_DELAY)
    client.write(encode_sequences([(A, delay), (termination + B, delay)]))
    data = client.read()
    assert data == A
    client.close()

# Test on_continuation='store'
def test_continuation_store():
    A = b'ABCDEFGH'
    B = b'IJKLMNOPQKRSTUVWXYZ'
    termination = b'*'
    delay = 0.5
    client = SerialPort(
        port=PORT,
        baudrate=BAUDRATE,
        timeout=Timeout(response=delay + TIME_DELTA, continuation=delay-TIME_DELTA, on_continuation='store'),
        stop_condition=Termination(termination)
        )
    sleep(OPEN_DELAY)
    client.write(encode_sequences([(A, delay), (termination + B, delay)]))
    data = client.read()
    assert data == b''
    data = client.read()
    assert data == A
    client.close()

# Test on_continuation='error'
def test_continuation_error():
    A = b'ABCDEFGH'
    B = b'IJKLMNOPQKRSTUVWXYZ'
    termination = b'*'
    delay = 0.5
    client = SerialPort(
        port=PORT,
        baudrate=BAUDRATE,
        timeout=Timeout(response=delay + TIME_DELTA, continuation=delay-TIME_DELTA, on_continuation='error'),
        stop_condition=Termination(termination)
        )
    sleep(OPEN_DELAY)
    client.write(encode_sequences([(A, delay), (termination + B, delay)]))
    try:
        data = client.read()
    except TimeoutException as te:
        assert te._type == Timeout.TimeoutType.CONTINUATION
    else:
        raise RuntimeError(f"No exception raised")
    client.close()