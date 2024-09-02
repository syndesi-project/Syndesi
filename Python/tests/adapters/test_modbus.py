from time import sleep
from syndesi import IP, Modbus
from random import randint

HOST = 'localhost'
PORT = 502

from syndesi import log_settings

log_settings('DEBUG')

modbus_client = Modbus(IP(HOST, port=PORT))

def test_read_coils():
    N_tests = 10000

    for _ in range(N_tests):
        N_coils = randint(1, 0x07B0)
        #address = 0x0001
        #N_coils = 1
        address = randint(0x0001, 0xFFFF - N_coils + 1)

        a_new_values = [bool(randint(0, 1)) for _ in range(N_coils)]
        modbus_client.write_multiple_coils(address, a_new_values)
        assert a_new_values == modbus_client.read_coils(address, N_coils)