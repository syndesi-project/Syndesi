# Syndesi Python Implementation

Syndesi description is available [here](https://github.com/syndesi-project/Syndesi/README.md)

## Installation

The syndesi Python package can be installed through pip

``pip install syndesi``

The package can also be installed locally by cloning this repository

```bash
git clone https://github.com/syndesi-project/Syndesi
cd Syndesi/Python
pip install .
```

## Usage



To instantiate a device, one must import the device and a suitable adapter

```python
# 1) Import the device
from syndesi.drivers.instruments.mutlimeters.siglent.SDM3055 import SDM3055
# 2) Import the adapter
from syndesi.adapters import IP

# 3) Instantiate the multimeter using its IP
mm = SDM3055(IP("192.168.1.123"))

## 4) Use
voltage = mm.measure_dc_voltage()
```
## Layers

The first layer is the "Device" base class

The second layer is made of "Primary drivers". First stage drivers implement mid-level communication protocols like Modbus, SDP, Raw, HTTP, SPCI, etc... Those drivers can be instanciated by the user if he wishes to use a device "as is" (i.e without an application driver)

Next are device drivers. They provide implementation for device-specific operations

Last are the application drivers. These are used to provide application-specific operations that mar or may not be tied to a particular device.

Note that both device drivers and application drivers can be omitted and can also be stacked as all first stage drivers, device drivers and application drivers stem from the same base Class

## SDP

The Syndesi Device Protocol is a light-weight and easy interface to send / receive commands with compatible devices.

## Usecases

- Test gear (multimeters, oscilloscopes, power supply, etc...)
  - set values (output voltage, settings, etc...)
  - get values (measured voltage, trace, screenshot)
  - continuously read data (UART multimeter for instance)
- UART devices (Arduinos, etc...)
  - Send / receive raw data
  - Custom drivers
- Syndesi devices
  - Send / receive formatted data
- USB devices
  - Send / receive data using the USB protocol

## Notes

06.09.2023 : bytearray is changed to bytes everywhere

23.10.2023 : continuation timeout isn't suitable for TCP, but it can work for UDP as a UDP server can send multiple response packets after a single packet from the client. This can be handled in different ways by firewalls. Thankfull that's none of our business so continuation timeout can be implemented

22.11.2023 : The timeout and stop conditions strategy is a bit complicated :

- What if we receive the message b'ACK\nNCK\n' using a termination stop condition but we receive b'ACK', then a timeout, then b'\nNCK\n' ?
  - Should the first part be kept ? should an error be raised at the timeout because nothing was read ?
    - Two kinds of timeouts ?
      - One where "we read as much as possible during the available time"
      - One where "we expect a response within X otherwise it's trash" 
