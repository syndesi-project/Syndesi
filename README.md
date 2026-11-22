# Syndesi

[![PyPI](https://img.shields.io/pypi/v/syndesi)](https://pypi.org/project/syndesi/)
[![Documentation](https://readthedocs.org/projects/syndesi/badge/?version=latest)](https://syndesi.readthedocs.io/en/latest/)

**Talk to any device in a few lines of Python.**

Syndesi gives instruments, PLCs, boards and sensors the same simple interface:
`write`, `read` and `query`. It works over TCP, UDP, serial ports, VISA, I2C and SPI,
and speaks SCPI, Modbus and line-based text out of the box, in sync or async code.

```python
from syndesi import IP, SCPI

scope = SCPI(IP("192.168.1.42"))   # port 5025 and "\n" termination: SCPI knows its defaults
print(scope.query("*IDN?"))        # 'KEYSIGHT,DSOX1204G,CN6...,2.12'
```

📖 **Documentation: [syndesi.readthedocs.io](https://syndesi.readthedocs.io/en/latest/)**.
New to Syndesi? Start with the
[first tutorial](https://syndesi.readthedocs.io/en/latest/tutorials/first-connection.html):
it needs no hardware.

## Installation

```bash
pip install syndesi
```

Python 3.11 or newer. Optional extras:

```bash
pip install "syndesi[visa]"   # USB-TMC, GPIB and LXI instruments, through pyvisa
pip install "syndesi[ui]"     # the graphical bench, syndesi ui
```

## Three layers

Pick the layer you need, and stack them like building blocks.

**Adapters** carry `bytes`: `IP`, `SerialPort`, `Visa`, `IPServer`, `I2C`, `SPI`.

```python
from syndesi import SerialPort

arduino = SerialPort("/dev/ttyUSB0", 115200)   # "COM3" on Windows
arduino.query(b"get_temperature\n")             # b'20.5\n'
```

**Protocols** sit on an adapter and handle the message format: `Delimited` (text lines),
`SCPI`, `Modbus`, `Raw`.

```python
from syndesi import Delimited, Modbus, IP, SerialPort

arduino = Delimited(SerialPort("/dev/ttyUSB0", 115200))
float(arduino.query("get_temperature"))   # 20.5, the "\n" is added and removed for you

plc = Modbus(IP("192.168.1.50"))          # Modbus TCP, port 502
plc.read_holding_registers(1, 2)          # [1234, 42]
```

**Drivers** wrap a device in a class with methods named after what it does. Write your
own ([tutorial](https://syndesi.readthedocs.io/en/latest/tutorials/first-driver.html)),
or use the ones of [syndesi-drivers](https://github.com/syndesi-project/Drivers):

```python
from syndesi import IP
from syndesi_drivers.test_and_measurement.multimeters.siglent_sdm3055 import SiglentSDM3055

dmm = SiglentSDM3055(IP("192.168.1.123"))
dmm.measure_dc_voltage()
```

Every adapter and protocol has an async twin: `AsyncIP`, `AsyncSCPI`, `AsyncModbus`…

## Tools

```bash
syndesi term serial /dev/ttyUSB0 115200   # interactive terminal for any device
syndesi term serial --list                # which serial ports are there
syndesi-trace                             # watch every byte your scripts exchange, live
syndesi ui                                # graphical bench: stack layers, call methods
```

## Links

- [Documentation](https://syndesi.readthedocs.io/en/latest/), with
  [tutorials](https://syndesi.readthedocs.io/en/latest/tutorials/index.html) and
  [how-to guides](https://syndesi.readthedocs.io/en/latest/how-to/index.html)
- [Examples](https://github.com/syndesi-project/Syndesi/tree/main/examples), short scripts to run right away
- [Drivers](https://github.com/syndesi-project/Drivers), ready-made instrument drivers
- [Changelog](https://github.com/syndesi-project/Syndesi/blob/main/CHANGELOG.md)
- [Issues](https://github.com/syndesi-project/Syndesi/issues)

Syndesi is free software, under the [GPL-3.0](https://github.com/syndesi-project/Syndesi/blob/main/LICENSE) license.
