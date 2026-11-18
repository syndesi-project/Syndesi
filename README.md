# Syndesi Python Implementation

Syndesi is a modular Python framework designed to streamline communication and control of a wide range of electronic instruments and devices. By providing a unified abstraction layer for adapters, protocols, and device drivers, Syndesi enables seamless integration with test equipment such as multimeters, oscilloscopes, power supplies, UART/USB devices, and more. Its flexible architecture supports both high-level and low-level operations, making it ideal for automation, data acquisition, and custom device interfacing in laboratory, industrial, and research environments.

## Installation

The syndesi Python package can be installed through pip

``pip install syndesi``

The package can also be installed locally by cloning this repository

```bash
git clone https://github.com/syndesi-project/Syndesi
cd Syndesi
pip install .
```

## Usage

The user can work with any of the three following layers :

- Adapters : low-level communication (IP, UART, ...)
- Protocols : Encapsulated protocols (Delimited, Modbus, ...)
- Drivers : Device or application specific commands

### Adapters : low-level communication

Available adapters : ``IP``, ``SerialPort``, ``VISA``, ``I2C``, ``SPI``

```python
from syndesi import IP

my_adapter = IP('192.168.1.12', port=5025)

my_adapter.write(b'ping\n')

my_adapter.read() # -> b'pong'
```

```python
from syndesi import SerialPort

arduino = SerialPort('/dev/ttyUSB0', baudrate=115200) # COMx on Windows
arduino.query(b'get_temperature\n') # -> 20.5
```

I2C and SPI work on the machine's own bus (Linux) or on a bus provided by a bridge, the driver of a converter (MCP2221, custom board, ...)

```python
from syndesi import I2C, SPI

sensor = I2C('/dev/i2c-1', address=0x48)
sensor.transfer(b'\x00', read_length=2) # write the register, read 2 bytes

flash = SPI('/dev/spidev0.0')
flash.transfer(b'\x9f\x00\x00\x00') # -> 4 bytes received meanwhile
```

### Protocols : Message formatting

Available protocols : ``Raw``, ``Delimited``, ``SCPI``

```python
from syndesi import IP, Delimited

my_server = Delimited(IP('test.server.local', port=1234))

my_server.query('Hello world') # -> Hello world (\n is both added and removed by Delimited)

```

### Drivers : Device-specific operations

Official syndesi drivers are provided by the [syndesi-drivers](https://github.com/syndesi-project/Drivers) package

```python
from syndesi_drivers.test_and_measurement.multimeters.siglent_sdm3055 import SiglentSDM3055
from syndesi import IP

mm = SiglentSDM3055(IP("192.168.1.123"))

voltage = mm.measure_dc_voltage()
```
