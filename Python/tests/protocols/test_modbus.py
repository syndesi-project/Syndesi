from time import sleep
from syndesi import IP, Modbus
from random import randint

HOST = 'localhost'
PORT = 502

def test_discrete():
    # TODO : Add out of range values + check for errors
    modbus_client = Modbus(IP(HOST, port=PORT))

    N_tests = 1000

    for i in range(N_tests):
        N = randint(1, 0x07B0)
        address = randint(0x0001, 0xFFFF - N + 1)

        a_new_values = [bool(randint(0, 1)) for _ in range(N)]
        modbus_client.write_multiple_coils(address, a_new_values)
        assert a_new_values == modbus_client.read_coils(address, N)

        assert a_new_values == modbus_client.read_discrete_inputs(address, N)