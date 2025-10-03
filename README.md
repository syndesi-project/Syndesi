# Syndesi Python Implementation

Syndesi description is available [here](https://github.com/syndesi-project/Syndesi/README.md)

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

### Adapters

The adapter allows the user to read and write raw data through IP, serial and VISA

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

### Protocols

Protocols encapsulate and format data

```python
from syndesi import IP, Delimited

my_server = Delimited(IP('test.server.local', port=1234))

my_server.query('Hello world\n') # -> Hello world (\n is removed by Delimited)

```

### Drivers

A driver only requires an adapter, the protocol (if used) is instanciated internally

```python
from syndesi_drivers.instruments.mutlimeters.siglent.SDM3055 import SDM3055
from syndesi.adapters import IP

mm = SDM3055(IP("192.168.1.123"))

voltage = mm.measure_dc_voltage()
```
