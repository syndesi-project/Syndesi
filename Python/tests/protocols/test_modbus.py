from time import sleep
from syndesi import IP, Modbus
from random import randint
import pytest
import subprocess
import signal
import os


## test_discrete 
# read_coils
# read_single_coil
# read_discrete_inputs
# write_single_coil
# write_multiple_coils

## test_registers
# write_multiple_registers
# read_holding_registers
# write_single_register
# read_single_register

## 

## Untested
# read_multi_register_value
# read_input_registers
# read_exception_status
# diagnostics_return_query_data
# diagnostics_restart_communications_option
# diagnostics_return_diagnostic_register
# diagnostics_change_ascii_input_delimiter
# diagnostics_force_listen_only_mode
# diagnostics_clear_counters_and_diagnostic_register
# diagnostics_return_bus_message_count
# diagnostics_return_bus_communication_error_count
# diagnostics_return_bus_exception_error_count
# diagnostics_return_server_no_response_count
# diagnostics_return_server_nak_count
# diagnostics_return_server_busy_count
# diagnostics_return_bus_character_overrun_count
# diagnostics_clear_overrun_counter_and_flag
# get_comm_event_counter
# get_comm_event_log
# report_server_id
# read_file_record
# write_file_record
# mask_write_register
# read_write_multiple_registers
# read_fifo_queue
# encapsulated_interface_transport

HOST = 'localhost'
PORT = 5555 # Use a port outside of reserved range, otherwise the diagslave server cannot be started
modbus_server = None

MIN_ADDRESS = 1
MAX_ADDRESS = 0xFFFF

# Initialize modbus server
def setup_module(module):
    global modbus_server
    modbus_server = subprocess.Popen(['diagslave', '-m', 'tcp', '-p', str(PORT)], stdout=subprocess.DEVNULL)
    sleep(0.2)

def teardown_module(module):
    global modbus_server
    os.kill(modbus_server.pid, signal.SIGINT)
    pass


def test_discrete():
    MIN_N = 1
    MAX_N = 0x07B0    
    modbus_client = Modbus(IP(HOST, port=PORT))

    N_tests = 1000

    for i in range(N_tests):
        N = randint(MIN_N - 5, MAX_N + 100)
        address = randint(MIN_ADDRESS - 5, MAX_ADDRESS + 100)

        single_value = bool(randint(0,1))
        new_values = [bool(randint(0, 1)) for _ in range(N)]
        number_of_coils_error = not (MIN_N <= N <= MAX_N)
        start_address_error = not (MIN_ADDRESS <= address <= MAX_ADDRESS)
        end_address_error = address > MAX_ADDRESS - N + 1

        if number_of_coils_error or start_address_error or end_address_error:
            with pytest.raises(AssertionError):
                modbus_client.write_multiple_coils(address, new_values)
            with pytest.raises(AssertionError):
                modbus_client.read_coils(address, N)
            with pytest.raises(AssertionError):
                modbus_client.read_discrete_inputs(address, N)
            
        else:
            modbus_client.write_multiple_coils(address, new_values)
            assert new_values == modbus_client.read_coils(address, N)
            assert new_values == modbus_client.read_discrete_inputs(address, N)

        if start_address_error:
            with pytest.raises(AssertionError):
                modbus_client.write_single_coil(address, single_value)
            with pytest.raises(AssertionError):
                modbus_client.read_single_coil(address)
        else:
            modbus_client.write_single_coil(address, single_value)
            modbus_client.read_single_coil(address)

def test_registers():
    modbus_client = Modbus(IP(HOST, port=PORT))

    MIN_N = 1
    MAX_N = 123

    N_tests = 1000

    for i in range(N_tests):
        N = randint(MIN_N - 5, MAX_N + 5)
        address = randint(MIN_ADDRESS - 5, MAX_ADDRESS + 100)

        single_value = bool(randint(0,0xFFFF))
        new_values = [int(randint(0, 0xFFFF)) for _ in range(N)]
        number_of_registers = not (MIN_N <= N <= MAX_N)
        start_address_error = not (MIN_ADDRESS <= address <= MAX_ADDRESS)
        end_address_error = address > MAX_ADDRESS - N + 1

        if number_of_registers or start_address_error or end_address_error:
            with pytest.raises(AssertionError):
                modbus_client.write_multiple_registers(address, new_values)
            with pytest.raises(AssertionError):
                modbus_client.read_holding_registers(address, N)
            
        else:
            modbus_client.write_multiple_registers(address, new_values)
            assert new_values == modbus_client.read_holding_registers(address, N)

        if start_address_error:
            with pytest.raises(AssertionError):
                modbus_client.write_single_register(address, single_value)
            with pytest.raises(AssertionError):
                modbus_client.read_single_register(address)
        else:
            modbus_client.write_single_register(address, single_value)
            modbus_client.read_single_register(address)