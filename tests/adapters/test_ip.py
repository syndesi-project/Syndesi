import logging
import random
from time import sleep
import time

from syndesi import IP
from syndesi.adapters.adapter import Frame
from syndesi.adapters.stop_conditions import *
from syndesi.adapters.timeout import Timeout
import socket
import os
import shutil
import sys
import subprocess

import pytest

from pathlib import Path

from syndesi.tools.errors import AdapterTimeoutError
HOST = "localhost"
PORT = 8888

def _compile_ip_delayer() -> Path:
    src = Path(__file__).parent / 'ip_delayer.cpp'
    build = src.parent / "build"
    build.mkdir(exist_ok=True)
    exe = build / ("ip_delayer.exe" if os.name == "nt" else "ip_delayer")

    def needs_build():
        return (not exe.exists()) or (exe.stat().st_mtime < src.stat().st_mtime)

    if not needs_build():
        return exe

    cxx = shutil.which("c++") or shutil.which("clang++") or shutil.which("g++")
    if not cxx:
        if sys.platform == "win32" and shutil.which("cl"):
            cmd = ["cl", "/O2", "/std:c++17", str(src), "/Fe:" + str(exe)]
            subprocess.check_call(cmd, cwd=build)
            return exe
        raise RuntimeError(
            "No C++ compiler found (need c++, clang++, g++, or cl on Windows)."
        )

    cmd = [cxx, "-O2", "-std=c++17", str(src), "-o", str(exe)]
    if sys.platform == "win32":
        cmd += ["-lws2_32"]
    # Show what we’re compiling for easier debugging
    subprocess.check_call(cmd)
    return exe


def _wait_port_open(port: int, timeout: float = 5.0) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            s = socket.create_connection(("127.0.0.1", port), 0.2)
            s.close()
            return True
        except OSError:
            time.sleep(0.05)
    return False


# @pytest.fixture(scope="module", autouse=True)
# def background_proc():
#     """Build and start ip_delayer once before tests."""
#     global _PROC, _PATH
#     _PATH = str(_compile_ip_delayer())
#     _PROC = subprocess.Popen(
#         [_PATH, "--port", str(PORT)],
#         #stdout=subprocess.STDOUT,
#         #stderr=subprocess.STDOUT,
#         #text=True,
#     )
#     if not _wait_port_open(PORT, timeout=5.0):
#         try:
#             out = _PROC.communicate(timeout=0.5)[0]
#         except Exception:
#             out = ""
#         _PROC.kill()
#         raise RuntimeError(
#             f"ip_delayer failed to start on port {PORT}. Output:\n{out}"
#         )

@pytest.fixture(scope="module", autouse=True)
def background_proc():
    """Build and start ip_delayer once before tests, kill it afterwards."""
    global _PROC, _PATH

    _PATH = str(_compile_ip_delayer())
    proc = subprocess.Popen(
        [_PATH, "--port", str(PORT)],
        # stdout=subprocess.STDOUT,
        # stderr=subprocess.STDOUT,
        # text=True,
    )
    _PROC = proc

    if not _wait_port_open(PORT, timeout=5.0):
        try:
            out = proc.communicate(timeout=0.5)[0]
        except Exception:
            out = ""
        proc.kill()
        proc.wait(timeout=5)
        raise RuntimeError(
            f"ip_delayer failed to start on port {PORT}. Output:\n{out}"
        )

    # ---- tests using the fixture run after this yield ----
    try:
        yield proc
    finally:
        # ---- teardown: called when all tests in the module are done ----
        if proc.poll() is None:  # still running
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)

def encode_sequences(sequences: list):
    output = b""
    for sequence, delay in sequences:
        output += sequence + b"," + f"{delay:.3f}".encode("ASCII") + b";"
    return output


TIME_DELTA = 50e-3

# Test response timeout
# long enough to catch the first sequence
def test_response_A():
    # This should catch the first sequence
    delay = 0.25
    sequence = b"ABCD"
    client = IP(
        HOST,
        port=PORT,
        timeout=Timeout(delay + TIME_DELTA, action="error"),
        stop_conditions=Continuation(0.1),
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
    sequence = b"ABCDE"
    client = IP(
        HOST,
        port=PORT,
        timeout=Timeout(response=delay - TIME_DELTA, action="return_empty"),
        stop_conditions=Continuation(0.1),
    )
    data = client.query(encode_sequences([(sequence, delay)]))
    assert data == b''
    sleep(2 * TIME_DELTA)
    data = client.read()
    assert data == sequence
    client.flush_read()
    client.close()


# Test continuation timeout
# Long enough to catch the first two sequences
def test_continuation():
    delay_response = 0.25
    sequence_response = b"ABCDE"
    delay_continuation = 0.3
    sequence_continuation = b"FGHIJKL"

    client = IP(
        HOST,
        port=PORT,
        timeout=delay_response + TIME_DELTA,
        stop_conditions=Continuation(
            continuation=delay_continuation + TIME_DELTA
        ),
        transport="udp",
    )
    data = client.query(
        encode_sequences(
            [
                (sequence_response, delay_response),
                (sequence_continuation, delay_continuation),
            ]
        )
    )
    assert data == sequence_response + sequence_continuation
    client.flush_read()
    client.close()

# Test termination
def test_termination():
    delay = 0.25
    A = b"AAAA"
    B = b"BBBB"
    termination = b"X"
    sequence = A + termination + B + termination

    client = IP(
        HOST,
        port=PORT,
        timeout=Timeout(response=delay + TIME_DELTA),
        stop_conditions=Termination(termination),
        transport="UDP"
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

    client = IP(
        HOST,
        port=PORT,
        timeout=Timeout(response=delay + TIME_DELTA),
        stop_conditions=Termination(termination),
        transport="UDP",
    )
    client.write(
        encode_sequences(
            [
                (A + termination[:1], delay),
                (termination[1:] + B + termination, delay + 5e-3),
            ]
        )
    )
    data = client.read()
    assert data == A + termination
    sleep(delay + TIME_DELTA)
    data = client.read()
    assert data == B + termination
    client.flush_read()
    client.close()


# Test length
def test_length():
    sequence = b"ABCDEFGHIJKLMNOPQKRSTUVWXYZ"
    N = 10
    client = IP(HOST, port=PORT, stop_conditions=Length(10))
    client.write(encode_sequences([(sequence, 0)]))
    data = client.read()
    assert data == sequence[:10]
    data = client.read()
    assert data == sequence[10:20]
    client.flush_read()
    client.close()

# Test length with short timeout
def test_length_short_timeout():
    sequence = b"ABCDEFGHIJKLMNOPQKRSTUVWXYZA"
    N = 10
    delay = 0.5
    client = IP(
        HOST,
        port=PORT,
        timeout=Timeout(response=delay - TIME_DELTA, action="return_empty"),
        stop_conditions=[Length(10), Continuation(0.1)],
    )
    data = client.query(encode_sequences([(sequence, delay)]))
    assert data == b''
    data = client.read()
    assert data == sequence[:N]
    data = client.read()
    assert data == sequence[N : 2 * N]
    data = client.read()  # Too short
    assert data == sequence[2*N:]
    client.flush_read()
    client.close()


# Test length with long timeout
def test_length_long_timeout():
    sequence = b"ABCDEFGHIJKLMNOPQKRSTUVWXYZ"
    N = 10
    delay = 0.5
    client = IP(
        HOST,
        port=PORT,
        timeout=Timeout(response=delay + TIME_DELTA, action="return_empty"),
        stop_conditions=[Length(10), Continuation(0.1)],
    )
    client.write(encode_sequences([(sequence, delay)]))
    data = client.read()
    assert data == sequence[:N]
    data = client.read()
    assert data == sequence[N : 2 * N]
    data = client.read()
    assert data == sequence[2*N:]

    client.close()


# Test termination with long timeout
def test_termination_long_timeout():
    A = b"ABCDEFGH"
    B = b"IJKLMNOPQKRSTUVWXYZ"
    termination = b"\n"
    delay = 0.5
    client = IP(
        HOST,
        port=PORT,
        timeout=Timeout(response=delay + TIME_DELTA),
        stop_conditions=Termination(termination),
        transport="UDP",
    )
    client.write(encode_sequences([(A, delay), (termination + B, delay + 1e-3)]))
    data = client.read()
    assert data == A + termination
    client.close()


# Return on a termination then a continuation timeout
def test_double_stop_condition():
    A = b"ABCDEFGH"
    B = b"IJKLMNOPQKRSTUVWXYZ"
    termination = b"\n"
    delay = 0.5
    client = IP(
        HOST,
        port=PORT,
        timeout=delay + TIME_DELTA,
        stop_conditions=[
            Termination(termination),
            Continuation(delay-TIME_DELTA)
        ],
        transport="UDP",
    )
    data = client.query(encode_sequences([(A, delay), (termination + B, delay + 1e-3)]))
    assert data == A + termination
    data = client.read()
    assert data == B
    client.close()


# # Test return timeout (too short)
# def test_return_timeout_short():
#     A = b"ABCDEFGH"
#     B = b"IJKLMNOPQKRSTUVWXYZ"
#     termination = b"\n"
#     delay = 0.5
#     client = IP(
#         HOST,
#         port=PORT,
#         timeout=Timeout(
#             response=delay + TIME_DELTA
#         ),  # continuation=delay-TIME_DELTA, on_continuation='return'
#         stop_conditions=Termination(termination),
#         transport="UDP",
#     )
#     client.write(encode_sequences([(A, delay), (termination + B, delay)]))
#     data = client.read()
#     assert data == A
#     client.close()


# # Test return timeout (long enough)
# def test_return_timeout_long():
#     A = b"ABCDEFGH"
#     B = b"IJKLMNOPQKRSTUVWXYZ"
#     termination = b"\n"
#     delay = 0.5
#     client = IP(
#         HOST,
#         port=PORT,
#         timeout=Timeout(
#             response=delay + TIME_DELTA
#         ),  # continuation=delay+TIME_DELTA, on_continuation='return'
#         stop_conditions=Termination(termination),
#         transport="UDP",
#     )
#     client.write(encode_sequences([(A, delay), (termination + B, delay)]))
#     data = client.read()
#     assert data == A
#     data = client.read()
#     assert data == B
#     client.close()


def test_timeout_on_return():
    A = b"ABCDEFGH"
    termination = b"\n"
    delay = 0.5
    client = IP(
        HOST,
        port=PORT,
        timeout=Timeout(response=delay - TIME_DELTA, action="return_empty"),
        stop_conditions=Termination(termination),
        transport="UDP",
    )
    client.write(encode_sequences([(A, delay)]))
    data = client.read()
    assert data == b''
    sleep(TIME_DELTA*2)
    client.flush_read()
    client.close()


# Test action='error'
def test_on_response_error():
    A = b"ABCDEFGH"
    termination = b"\n"
    delay = 0.5
    client = IP(
        HOST,
        port=PORT,
        timeout=Timeout(response=delay - TIME_DELTA),
        stop_conditions=Termination(termination),
        transport="UDP",
    )
    client.write(encode_sequences([(A + termination, delay)]))
    try:
        client.read()
    except AdapterTimeoutError as te:
        pass
    else:
        raise RuntimeError("No exception raised")
    data = client.read()
    assert data == A + termination
    client.flush_read()
    client.close()


# # Test on_continuation='discard'
# def test_continuation_discard():
#     A = b"ABCDEFGH"
#     B = b"IJKLMNOPQKRSTUVWXYZ"
#     termination = b"\n"
#     delay = 0.5
#     client = IP(
#         HOST,
#         port=PORT,
#         timeout=Timeout(
#             response=delay + TIME_DELTA
#         ),  # continuation=delay-TIME_DELTA, on_continuation='discard'
#         stop_conditions=Termination(termination),
#         transport="UDP",
#     )
#     client.write(encode_sequences([(A, delay), (termination + B, delay)]))
#     data = client.read()
#     assert data == b""
#     client.close()


# Test on_continuation='return'
def test_continuation_return():
    A = b"ABCDEFGH"
    B = b"IJKLMNOPQKRSTUVWXYZ"
    termination = b"\n"
    delay = 0.5
    client = IP(
        HOST,
        port=PORT,
        timeout=Timeout(
            response=delay + TIME_DELTA, action="return_empty"
        ),
        stop_conditions=[
            Termination(termination),
            Continuation(delay-TIME_DELTA)
        ],
        transport="UDP",
    )
    client.write(encode_sequences([(A, delay), (termination + B, 2*delay)]))
    data = client.read()
    assert data == A
    data = client.read()
    assert data == termination
    data = client.read()
    assert data == B
    client.flush_read()
    client.close()

# Test if a new configuration is correctly applied
def test_read_timeout_reconfiguration():
    A = b"ABCDEFGH"
    B = b"IJKLMNOPQKRSTUVWXYZ"
    termination = b"\n"
    delay = 0.5
    client = IP(
        HOST,
        port=PORT,
        timeout=Timeout(
            response=0,
        ),
        stop_conditions=Termination(termination),
        transport="UDP",
    )
    client.write(encode_sequences([(A+termination, delay)]))
    data = client.read(
        timeout=Timeout(
            response=delay + TIME_DELTA,
        )
    )
    assert data == A + termination
    client.write(encode_sequences([(B+termination, delay)]))
    data = client.read(
        timeout=Timeout(
            response=delay-TIME_DELTA, action="return_empty"
        )
    )
    assert data == b''
    client.flush_read()
    client.close()


def test_flush():
    A = b"AAAAAAAA"
    B = b"XXXXXXXX"

    client = IP(HOST, port=PORT, timeout=Timeout(response=1))

    client.write(encode_sequences([(A, 0)] * 3))
    sleep(1)
    client.flush_read()
    sleep(0.2)
    client.write(encode_sequences([(B, 0)]))
    data = client.read()
    assert data == B

def _test_delayer(ip_delayer_port):
    sequence = b'ABCD'
    N = 100
    client = IP(
        HOST,
        port=ip_delayer_port,
        timeout=Timeout(1 + TIME_DELTA, action='error'),
        stop_conditions=Continuation(0.005),
        transport='UDP')
    for _ in range(N):
        delay = random.random()*0.5
        frame = client.query_detailed(encode_sequences([(sequence, delay)]))
        data = frame.get_payload()
        frame : Frame
        assert data == sequence
        assert abs(frame.response_delay - delay) < TIME_DELTA
    client.flush_read()
    client.close()