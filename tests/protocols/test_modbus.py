from contextlib import ExitStack, contextmanager
import itertools
from pathlib import Path
import random
import shutil
import socket
import subprocess
import time
from random import randint, random
import pytest

from modbus_device import virtual_serial_pair

from syndesi import IP, Modbus
from syndesi.adapters.serialport import SerialPort
from syndesi.protocols.modbus import ModbusMultiRegisterValue

HOST = "localhost"
PORT = 5555  # Use a port outside of reserved range, otherwise the diagslave server cannot be started

MIN_ADDRESS = 1
MAX_ADDRESS = 0xFFFF
SLAVE_ADDRESS = 12

def pytest_addoption(parser):
    parser.addoption("--diagslave", default=None,
                     help="Path to diagslave executable")

def _wait_ready(proc, host, port, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"diagslave stopped (code {proc.returncode})")
        try:
            with socket.create_connection((host, port), timeout=0.2):
                return
        except OSError:
            time.sleep(0.05)
    raise TimeoutError(f"Diagslave doesn't listen on {host}:{port}")

ZERO_ADDRESS_ERROR = r"Invalid address : 0, it must be in the range \[1,65535\]"
ZERO_IO_ERROR = r"Invalid number of inputs/outputs : 0, it must be in the range \[1, 1968\]"


ALL_PROTOCOLS = ["rtu", "ascii", "tcp"]
#ALL_PROTOCOLS = ["tcp"]
SERIAL_PROTOCOLS = ["rtu", "ascii"]
SERIAL_ARGS = ["-a", str(SLAVE_ADDRESS), "-b", "19200", "-p", "even"]   # the client must use the same settings


# def pytest_configure(config):
#     config.addinivalue_line("markers", "serial_only: test runs only on RTU/ASCII")


def pytest_generate_tests(metafunc):
    if "modbus_endpoint" in metafunc.fixturenames:
        serial = metafunc.definition.get_closest_marker("serial_only")
        protocols = SERIAL_PROTOCOLS if serial else ALL_PROTOCOLS
        metafunc.parametrize("modbus_endpoint", protocols,
                             indirect=True, scope="session")


@pytest.fixture(scope="session")
def diagslave_path(request):
    try:
        path = request.config.getoption("--diagslave")
    except ValueError:
        path = shutil.which("diagslave")

    if path is None:
        pytest.fail("diagslave not found: add it to PATH or use --diagslave")
    return path


@contextmanager
def run_process(cmd):
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        yield proc
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()

@pytest.fixture(scope="session")
def modbus_endpoint(request, diagslave_path):
    protocol = request.param
    with ExitStack() as stack:
        if protocol == "tcp":
            proc = stack.enter_context(run_process(
                [diagslave_path, "-m", "tcp", "-p", str(PORT)]
            ))
            _wait_ready(proc, HOST, PORT)
            yield protocol, (HOST, PORT)
        else:
            srv_tty, cli_tty = stack.enter_context(virtual_serial_pair())
            stack.enter_context(run_process(
                [diagslave_path, "-m", protocol, *SERIAL_ARGS, srv_tty]))
            time.sleep(0.3)   # no TCP port to probe, give diagslave time to open the port
            yield protocol, cli_tty

@pytest.fixture
def modbus_client(modbus_endpoint):
    protocol, endpoint = modbus_endpoint
    if protocol == "tcp":
        host, port = endpoint
        return Modbus(IP(host, port=port))
    # adapt to your library's serial API:
    return Modbus(
        SerialPort(endpoint, baudrate=19200, parity="E"),
        serial_type=protocol,
        slave_address=SLAVE_ADDRESS
    )

def test_discrete(modbus_client : Modbus):
    MIN_N = 1
    MAX_N = 0x07B0

    n_random_tests = 5

    n_values = [-1, 0, MIN_N, MAX_N, MAX_N+1] + [randint(MIN_N, MAX_N) for _ in range(n_random_tests)]
    address_values = [-1, 0, MIN_ADDRESS, MAX_ADDRESS, MAX_ADDRESS+1] + [randint(MIN_ADDRESS, MAX_ADDRESS) for _ in range(n_random_tests)]

    for n, address in itertools.product(n_values, address_values):
        single_value = bool(randint(0, 1))
        new_values = [bool(randint(0, 1)) for _ in range(n)]
        number_of_coils_error = not (MIN_N <= n <= MAX_N)
        start_address_error = not (MIN_ADDRESS <= address <= MAX_ADDRESS)
        end_address_error = address > MAX_ADDRESS - n + 1

        if number_of_coils_error or start_address_error or end_address_error:
            with pytest.raises(ValueError):
                modbus_client.write_multiple_coils(address, new_values)
            with pytest.raises(ValueError):
                modbus_client.read_coils(address, n)
            with pytest.raises(ValueError):
                modbus_client.read_discrete_inputs(address, n)

        else:
            modbus_client.write_multiple_coils(address, new_values)
            assert new_values == modbus_client.read_coils(address, n)
            assert new_values == modbus_client.read_discrete_inputs(address, n)

        if start_address_error:
            with pytest.raises(ValueError):
                modbus_client.write_single_coil(address, single_value)
            with pytest.raises(ValueError):
                modbus_client.read_single_coil(address)
        else:
            modbus_client.write_single_coil(address, single_value)
            modbus_client.read_single_coil(address)

def test_registers(modbus_client : Modbus):
    #modbus_client = Modbus(IP(HOST, port=PORT))

    MIN_N = 1
    MAX_N = 123

    #N_tests = 1000

    # max number of registers for each command
    # write_multiple_registers : 123
    # read_write_multiple_registers (write) : 121
    # read_write_multiple_registers (read) : 125
    # read_holding_registers : 125

    address_range = [MIN_ADDRESS - 5, 0, 12, MAX_ADDRESS, MAX_ADDRESS + 1, MAX_ADDRESS + 100]
    n_registers_range = [MIN_N - 5, MIN_N, 50, MAX_N, MAX_N + 1, MAX_N + 100]
    for address in address_range:

        address_error = not (MIN_ADDRESS <= address <= MAX_ADDRESS)


        # Test :
        # - write_single_register
        # - read_single_register

        single_value_range = [-5, 0, 123, 0xFFFF, 0xFFFF+1]
        for single_value in single_value_range:
            single_value_error = not (0 <= single_value <= 0xFFFF)
            if address_error or single_value_error:
                with pytest.raises(ValueError):
                    modbus_client.write_single_register(address, single_value)
            if address_error:
                with pytest.raises(ValueError):
                    modbus_client.read_single_register(address)
            else:
                if single_value_error:
                    with pytest.raises(ValueError):    
                        modbus_client.write_single_register(address, single_value)
                else:
                    modbus_client.write_single_register(address, single_value)
                first_value = modbus_client.read_single_register(address)

        # Test :
        # - mask_write_register
        # Test mask_write by applying a random AND and a random OR mask to the first value
        AND = randint(0, 0xFFFF)
        OR = randint(0, 0xFFFF)
        if address_error:
            with pytest.raises(ValueError):
                modbus_client.mask_write_register(address, and_mask=AND, or_mask=OR)
        else:
            modbus_client.mask_write_register(address, and_mask=AND, or_mask=OR)
            masked_value = modbus_client.read_single_register(address)
            assert masked_value == (first_value & AND) | (OR & ~AND)

        # Test :
        # - write_multiple_registers
        for n in n_registers_range:
            n_register_error = not (MIN_N <= n <= MAX_N)
            new_values = [int(randint(0, 0xFFFF)) for _ in range(n)]
            address_error |= address > MAX_ADDRESS - n + 1

            if address_error or n_register_error:
                with pytest.raises(ValueError):
                    modbus_client.write_multiple_registers(address, new_values)
            else:
                modbus_client.write_multiple_registers(address, new_values)

            # Test:
            # - read_holding_registers
            if n < 1 or n > 125 or address_error:
                with pytest.raises(ValueError):
                    modbus_client.read_holding_registers(address, n)
            else:
                # If N is bigger than 123, do not do the test because the write did not succeed
                if n <= 123:
                    assert new_values == modbus_client.read_holding_registers(address, n)

            # Test :
            # - read_write_multiple_registers
            if (
                n < 1 or n > 121 or address_error
            ):  # Write limit because read and write are the same here
                with pytest.raises(ValueError):
                    read_values = modbus_client.read_write_multiple_registers(
                        address, n, address, new_values
                    )

            else:
                read_values = modbus_client.read_write_multiple_registers(
                    address, n, address, new_values
                )
                assert read_values == new_values

            if 1 <= n <= 125 and not address_error:
                modbus_client.read_input_registers(address, n)
            else:
                with pytest.raises(ValueError):
                    modbus_client.read_input_registers(address, n)

def test_multi_register_values(modbus_client : Modbus):

    # Test byte_order and word_order combinations (+ int values for a 4 byte test)
    for word_order, byte_order, reg_0, reg_1 in [
        ("big", "big", 0x0A0B, 0x0C0D),
        ("big", "little", 0x0B0A, 0x0D0C),
        ("little", "big", 0x0C0D, 0x0A0B),
        ("little", "little", 0x0D0C, 0x0B0A),
    ]: 
        address = MIN_ADDRESS
        value = 0x0A0B0C0D
        n_registers = 2
        modbus_client.write_multi_register_value(
            address,
            ModbusMultiRegisterValue.from_uint(
                value,
                n_registers=n_registers,
                byte_order=byte_order,
                word_order=word_order
            )            
        )
        registers = modbus_client.read_holding_registers(
            address,
            n_registers=n_registers
            )
        assert registers == [reg_0, reg_1]

        read_value = modbus_client.read_multi_register_value(
            address,
            n_registers=2,
            byte_order=byte_order,
            word_order=word_order
        ).to_uint()
        assert read_value == value

        # Store a float
        n_registers = 2
        address = randint(MIN_ADDRESS, MAX_ADDRESS-n_registers+1)
        value = random()
        modbus_client.write_multi_register_value(
            address,
            ModbusMultiRegisterValue.from_float(
                value,
                n_registers=n_registers,
                word_order=word_order,
                byte_order=byte_order
            )
        )
        read_value = modbus_client.read_multi_register_value(
            address,
            n_registers,
            byte_order=byte_order,
            word_order=word_order
        ).to_float()
        assert abs(value - read_value) < 1e-7

        # Store a string
        n_registers = 10
        address = randint(MIN_ADDRESS, MAX_ADDRESS)
        data = "this is a test"
        # This should fail (input too long)
        with pytest.raises(ValueError):
            modbus_client.write_multi_register_value(
                address,
                ModbusMultiRegisterValue.from_string(data*3, n_registers=n_registers)
            )

        modbus_client.write_multi_register_value(
            address,
            ModbusMultiRegisterValue.from_string(
                data,
                n_registers=n_registers
            )
        )
        read_string = modbus_client.read_multi_register_value(
            address,
            n_registers=n_registers
        ).to_string()
        assert read_string == data

        address = randint(MIN_ADDRESS, MAX_ADDRESS)
        data = b"0123456789ABCDEFGHIJ"
        n_registers = 10

        # break
        modbus_client.write_multi_register_value(
            address,
            ModbusMultiRegisterValue.from_array(
                data,
                n_registers=n_registers,
                byte_order=byte_order,
                word_order=word_order
            )
        )
        read_array = modbus_client.read_multi_register_value(
            address,
            n_registers=n_registers,
            byte_order=byte_order,
            word_order=word_order
        ).to_array()
        assert read_array == data

@pytest.mark.serial_only
def test_serial_only(modbus_client : Modbus):
    status = modbus_client.read_exception_status()
