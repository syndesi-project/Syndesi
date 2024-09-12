from time import sleep
from syndesi import IP, Modbus
from random import randint
import pytest
import subprocess
import signal
import os

HOST = 'localhost'
PORT = 5555 # Use a port outside of reserved range, otherwise the diagslave server cannot be started
modbus_server = None

# Initialize modbus server
def setup_module(module):
    global modbus_server
    modbus_server = subprocess.Popen(['diagslave', '-m', 'tcp', '-p', str(PORT)])

def teardown_module(module):
    global modbus_server
    os.kill(modbus_server.pid, signal.SIGINT)


def test_discrete():
    MIN_N = 1
    MAX_N = 0x07B0
    MIN_ADDRESS = 1
    MAX_ADDRESS = 0xFFFF
    # TODO : Add out of range values + check for errors
    modbus_client = Modbus(IP(HOST, port=PORT))

    N_tests = 1000

    for i in range(N_tests):
        N = randint(MIN_N - 5, MAX_N + 100)
        address = randint(MIN_ADDRESS - 5, MAX_ADDRESS + 100)

        a_new_values = [bool(randint(0, 1)) for _ in range(N)]
        expect_error = not ((MIN_N <= N <= MAX_N) and (MIN_ADDRESS <= address <= MAX_ADDRESS - N + 1))  

        print(f'Start address : {address}, N : {N}, error : {expect_error}')
        if expect_error:
            with pytest.raises(AssertionError):
                modbus_client.write_multiple_coils(address, a_new_values)    
            with pytest.raises(AssertionError):
                modbus_client.read_coils(address, N)
            with pytest.raises(AssertionError):
                modbus_client.read_discrete_inputs(address, N)
        else:
            modbus_client.write_multiple_coils(address, a_new_values)
            assert a_new_values == modbus_client.read_coils(address, N)
            assert a_new_values == modbus_client.read_discrete_inputs(address, N)
