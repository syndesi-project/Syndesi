from time import sleep, time

# from syndesi.adapters.backend.timeout import TimeoutType
from serial_delayer import SerialDelayer

import pytest

from syndesi import SerialPort
from syndesi.adapters.stop_conditions import Length, Termination, Continuation
from syndesi.adapters.timeout import Timeout
from syndesi.tools.errors import AdapterOpenError, AdapterTimeoutError

BAUDRATE = 115200
TIME_DELTA = 30e-3

delayer: SerialDelayer
delayer = None
PORT: str
PORT = None


def setup_module(module):
    global delayer, PORT
    delayer = SerialDelayer()
    PORT = delayer.port()


def teardown_module(module):
    global delayer
    if delayer is not None:
        delayer.stop()


def encode_sequences(sequences: list):
    output = b""

    for data, delay in sequences:
        output += data + b"," + f"{delay * 1e3:.0f}".encode("ASCII") + b';'
    return output


def test_delayer():
    global delayer
    DATA = b"test_delayer"
    port = SerialPort(port=PORT, baudrate=1000000)
    port.write(encode_sequences([(DATA, 0.2)]))
    received = port.read(stop_conditions=Length(len(DATA)))
    assert received == DATA
    port.flush_read()
    port.close()


# Test response timeout
# long enough to catch the first sequence
def test_response_A():
    # This should catch the first sequence
    delay = 0.25
    sequence = b"ABCD"
    client = SerialPort(
        port=PORT, baudrate=BAUDRATE, timeout=delay + TIME_DELTA
    )
    client.write(encode_sequences([(sequence, delay)]))
    data = client.read()
    assert data == sequence
    client.flush_read()
    client.close()


# Test response timeout
# not long enough to catch the first sequence
def test_response_B():
    delay = 0.25
    sequence = b"test_B"
    client = SerialPort(
        port=PORT, baudrate=BAUDRATE, timeout=delay - TIME_DELTA
    )
    start = time()
    client.write(encode_sequences([(sequence, delay)]))
    try:
        data = client.read()
    except AdapterTimeoutError:
        pass  # This is what we expect
    else:
        raise RuntimeError("No timeout exception was raised")
    # sleep(2*TIME_DELTA)
    data = client.read()
    assert data == sequence
    client.flush_read()
    client.close()


# Test continuation timeout
# Long enough to catch the first two sequences
def test_continuation():
    delay_response = 0.25
    sequence_response = b"ABCDE"
    delay_continuation = 0.5
    sequence_continuation = b"FGHIJKL"

    client = SerialPort(
        port=PORT,
        baudrate=BAUDRATE,
        timeout=Timeout(
            response=delay_response + TIME_DELTA,
            action="error",
        ),
        stop_conditions=[
            Continuation(delay_continuation+TIME_DELTA)
        ]
    )

    client.write(
        encode_sequences(
            [
                (sequence_response, delay_response),
                (sequence_continuation, delay_response+delay_continuation),
            ]
        )
    )
    data = client.read()
    assert data == sequence_response + sequence_continuation
    client.flush_read()
    client.close()


def test_big():
    delay = 0.25
    sequence = 1000 * b"A"

    client = SerialPort(
        port=PORT,
        baudrate=BAUDRATE,
        timeout=Timeout(response=delay + TIME_DELTA)#continuation=TIME_DELTA),
    )

    client.write(encode_sequences([(sequence, delay)]))
    data = client.read()
    assert data == sequence
    client.flush_read()
    client.close()


# Test termination
def test_termination():
    delay = 0.25
    A = b"AAAA"
    B = b"BBBB"
    termination = b"X"
    sequence = A + termination + B + termination

    client = SerialPort(
        port=PORT,
        baudrate=BAUDRATE,
        timeout=Timeout(response=delay + TIME_DELTA),#, continuation=delay + TIME_DELTA),
        stop_conditions=Termination(termination),
    )

    client.write(encode_sequences([(sequence, delay)]))
    data = client.read()
    assert data == A + termination
    data = client.read()
    assert data == B + termination
    client.flush_read()
    client.close()


# Test termination with partial transmission of the termination
def test_termination_partial():
    delay = 0.25

    A = b"AAAA"
    B = b"BBBB"
    termination = b"XX"

    client = SerialPort(
        port=PORT,
        baudrate=BAUDRATE,
        timeout=Timeout(response=delay + TIME_DELTA),
        stop_conditions=[
            Termination(termination),
            Continuation(continuation=delay + TIME_DELTA)
        ],
    )

    client.write(
        encode_sequences(
            [(A + termination[:1], delay), (termination[1:] + B + termination, 2 * delay)]
        )
    )
    data = client.read()
    assert data == A + termination
    data = client.read()
    assert data == B + termination
    client.close()

# Test length
def test_length():
    sequence = b"ABBBBCDEFGHIJKLMNOPQKRSTUVWXYZ"
    N = 10
    client = SerialPort(port=PORT, baudrate=BAUDRATE, stop_conditions=Length(10))

    with pytest.raises(AdapterOpenError):
        SerialPort(port=PORT, baudrate=BAUDRATE, stop_conditions=Length(10))

    client.write(encode_sequences([(sequence, 0)]))
    data = client.read()
    assert data == sequence[:10]
    data = client.read()
    assert data == sequence[10:20]
    client.close()

# Test length with short timeout
def test_length_short_timeout():
    sequence = b"AABCDEFGHIJKLMNOPQKRSTUVWXYZ"
    N = 10
    delay = 0.5
    client = SerialPort(
        port=PORT,
        baudrate=BAUDRATE,
        timeout=Timeout(response=delay - TIME_DELTA),
        stop_conditions=Length(N),
    )

    client.write(encode_sequences([(sequence, delay)]))
    try:
        data = client.read()
    except AdapterTimeoutError:
        pass  # This is what we expect
    else:
        raise RuntimeError("No timeout exception was raised")
    data = client.read()
    assert data == sequence[:N]
    data = client.read(stop_conditions=Continuation(continuation=0.1))
    # Length is still N because that was read before
    assert data == sequence[N:N+10]
    client.flush_read()
    client.close()


# Test length with long timeout
def test_length_long_timeout():
    sequence = b"ABCDEFGHIJKLMNOPQKRSTUVWXYZAA"
    N = 10
    delay = 0.5
    client = SerialPort(
        port=PORT,
        baudrate=BAUDRATE,
        timeout=Timeout(response=delay + TIME_DELTA),
        stop_conditions=Length(N),
    )

    client.write(encode_sequences([(sequence, delay)]))
    data = client.read()
    assert data == sequence[:N]
    data = client.read()
    assert data == sequence[N:N+10]
    client.flush_read()
    client.close()


# Test termination with long timeout
def test_termination_long_timeout():
    A = b"ABCDEFGH"
    B = b"IJKLMNOPQKRSTUVWXYZ"
    termination = b"*"
    delay = 0.5
    client = SerialPort(
        port=PORT,
        baudrate=BAUDRATE,
        timeout=Timeout(response=delay + TIME_DELTA),
        stop_conditions=[Termination(termination), Continuation(continuation=delay + TIME_DELTA)]
    )

    client.write(encode_sequences([(A, delay), (termination + B, 2*delay)]))
    data = client.read()
    assert data == A + termination
    data = client.read()
    assert data == B
    client.flush_read()
    client.close()


# Test discard timeout (too short)
def test_discard_timeout_short():
    A = b"ABCDEFGH"
    B = b"IJKLMNOPQKRSTUVWXYZ"
    termination = b"*"
    delay = 0.5
    client = SerialPort(
        port=PORT,
        baudrate=BAUDRATE,
        timeout=Timeout(
            response=delay - TIME_DELTA,
        ),
        stop_conditions=[
            Termination(termination),
            Continuation(continuation=delay - TIME_DELTA)
            ]
    )

    client.write(encode_sequences([(A, delay), (termination + B, 2*delay)]))
    try:
        client.read()
    except AdapterTimeoutError:
        pass
    else:
        raise RuntimeError('Failed to raise error')
    
    data = client.read() # Continuation
    assert data == A
    data = client.read() # Termination
    assert data == termination
    data = client.read() # Continuation
    assert data == B
    client.flush_read()
    client.close()


# Test discard timeout (long enough)
def test_discard_timeout_long():
    A = b"ABCDEFGH"
    B = b"IJKLMNOPQKRSTUVWXYZ"
    termination = b"*"
    delay = 0.5
    client = SerialPort(
        port=PORT,
        baudrate=BAUDRATE,
        timeout=Timeout(
            response=delay + TIME_DELTA,
        ),
        stop_conditions=[
            Termination(termination),
            Continuation(continuation=delay + TIME_DELTA)
        ]
    )

    client.write(encode_sequences([(A, delay), (termination + B, 2*delay)]))
    data = client.read()
    assert data == A + termination
    sleep(2*delay)
    client.flush_read()
    client.close()


# Test return timeout (too short)
def test_return_timeout_short():
    A = b"ABCDEFGH"
    B = b"IJKLMNOPQKRSTUVWXYZ"
    termination = b"*"
    delay = 0.5
    client = SerialPort(
        port=PORT,
        baudrate=BAUDRATE,
        timeout=Timeout(
            response=delay + TIME_DELTA,
        ),
        stop_conditions=[
            Termination(termination),
            Continuation(continuation=delay - TIME_DELTA)
        ]
    )

    client.write(encode_sequences([(A, delay), (termination + B, 2 * delay)]))
    data = client.read()
    assert data == A
    data = client.read()
    assert data == termination
    data = client.read()
    assert data == B
    client.flush_read()
    client.close()


# Test return timeout (long enough)
def test_return_timeout_long():
    A = b"ABCDEFGH"
    B = b"IJKLMNOPQKRSTUVWXYZ"
    termination = b"*"
    delay = 0.5
    client = SerialPort(
        port=PORT,
        baudrate=BAUDRATE,
        timeout=Timeout(
            response=delay + TIME_DELTA
        ),
        stop_conditions=[
            Termination(termination),
            Continuation(continuation=delay+TIME_DELTA),
        ]
    )

    client.write(encode_sequences([(A, delay), (termination + B, delay)]))
    data = client.read()
    assert data == A + termination
    data = client.read()
    assert data == B
    client.flush_read()
    client.close()


# Test action=whatever except 'error'
# def test_response_no_error():
#     for r in ["discard", "return", "store"]:
#         A = b"ABCDEFGH"
#         B = b"IJKLMNOPQKRSTUVWXYZ"
#         termination = b"*"
#         delay = 0.5
#         client = SerialPort(
#             port=PORT,
#             baudrate=BAUDRATE,
#             timeout=Timeout(response=delay - TIME_DELTA, action=r),
#             stop_conditions=Termination(termination),
#         )
#         client.write(encode_sequences([(A, delay)]))
#         data = client.read()
#         assert data == b""
#         data = client.read()
#         client.flushRead()
#         client.close()


# Test action='error'
def test_response_error():
    A = b"ABCDEFGH"
    termination = b"*"
    delay = 0.5
    client = SerialPort(
        port=PORT,
        baudrate=BAUDRATE,
        timeout=Timeout(response=delay - TIME_DELTA, action="error"),
        stop_conditions=Termination(termination),
    )

    client.write(encode_sequences([(A + termination, delay)]))
    try:
        client.read()
    except AdapterTimeoutError as te:
        #assert te._type == TimeoutType.RESPONSE
        pass
    else:
        raise RuntimeError("No exception raised")
    data = client.read()
    assert data == A + termination
    client.flush_read()
    client.close()


# Test on_continuation='discard'
# def test_continuation_discard():
#     A = b"ABCDEFGHC"
#     B = b"IJKLMNOPQKRSTUVWXYZD"
#     termination = b"*"
#     delay = 0.5
#     client = SerialPort(
#         port=PORT,
#         baudrate=BAUDRATE,
#         timeout=Timeout(
#             response=delay + TIME_DELTA,
#             #continuation=delay - TIME_DELTA,
#             #on_continuation="discard",
#         ),
#         stop_conditions=[
#             Termination(termination),
#             Continuation(continuation=delay-TIME_DELTA)
#         ]
#     )

#     client.write(encode_sequences([(A, delay), (termination + B, delay)]))
#     data = client.read()
#     assert data == b""
#     data = client.read()#timeout=Timeout(on_continuation="return"))#stop_condition=None,
#     assert data == termination + B
#     client.flushRead()
#     client.close()


# Test on_continuation='return'
# def test_continuation_return():
#     A = b"ABCDEFGHAA"
#     B = b"IJKLMNOPQKRSTUVWXYZBB"
#     termination = b"*"
#     delay = 0.5
#     client = SerialPort(
#         port=PORT,
#         baudrate=BAUDRATE,
#         timeout=Timeout(
#             response=delay + TIME_DELTA,
#             #continuation=delay - TIME_DELTA,
#             #on_continuation="return",
#         ),
#         stop_conditions=Termination(termination),
#     )

#     client.write(encode_sequences([(A, delay), (termination + B, delay)]))
#     data = client.read()
#     assert data == A
#     data = client.read()#stop_condition=None)
#     assert data == termination + B
#     client.flushRead()
#     client.close()


# Test on_continuation='store'
# def test_continuation_store():
#     A = b"ABCDEFGHX"
#     B = b"IJKLMNOPQKRSTUVWXYZX"
#     termination = b"*"
#     delay = 0.5
#     client = SerialPort(
#         port=PORT,
#         baudrate=BAUDRATE,
#         timeout=Timeout(
#             response=delay + TIME_DELTA,
#             #continuation=delay - TIME_DELTA,
#             #on_continuation="store",
#         ),
#         stop_conditions=Termination(termination),
#     )

#     client.write(encode_sequences([(A, delay), (termination + B, delay)]))
#     data = client.read()
#     assert data == b""
#     data = client.read()
#     assert data == A
#     client.flushRead()
#     client.close()


# Test on_continuation='error'
# def test_continuation_error():
#     A = b"ABCDEFGH"
#     B = b"IJKLMNOPQKRSTUVWXYZ"
#     termination = b"*"
#     delay = 0.5
#     client = SerialPort(
#         port=PORT,
#         baudrate=BAUDRATE,
#         timeout=Timeout(
#             response=delay + TIME_DELTA,
#             #continuation=delay - TIME_DELTA,
#             #on_continuation="error",
#         ),
#         stop_conditions=Termination(termination),
#     )

#     client.write(encode_sequences([(A, delay), (termination + B, delay)]))
#     try:
#         data = client.read()
#     except AdapterTimeoutError:
#         pass
#         #assert te._type == TimeoutType.CONTINUATION
#     else:
#         raise RuntimeError("No exception raised")
#     client.flushRead()
#     client.close()


def test_flush():
    sleep(0.1)

    A = b"AAAAAAAA"
    B = b"XXXXXXXX"

    client = SerialPort(
        port=PORT, baudrate=BAUDRATE, timeout=Timeout(response=1)#, continuation=10e-3)
    )

    client.write(encode_sequences([(A, 0)] * 3))
    sleep(1)
    client.flush_read()
    sleep(0.2)
    client.write(encode_sequences([(B, 0)]))
    data = client.read()
    assert data == B
    client.flush_read()
    client.close()
