# Syndesi Python

The Syndesi Python package provides the user with the necessary tools to control compatible devices

- drivers : device-specific implementation
- descriptors : Each class represents a particular way of connecting to a device, the user must provide que necessary information (IP, com port, ID, etc...)
- communication wrapper (wrappers) : Wrappers for low-level communication (TCP, UDP, UART, etc...)
  - IP (TCP / UDP)
  - UART
  - USB (?)

## Notes

The user specifies a descriptor. The descriptor takes care of choosing the right wrapper and the correct implementation depending on the type of device

```python

mydevice = Device(RawTCP("182.168.1.12"))
mydevice = Device(SyndesiDevice("182.168.1.123"))
```

The Device is the base class, it doesn't implement any session protocol, only the one(s) necessary to communicate with it.

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

## Notes (obsolete)

The user could specify the wrapper directly (IP, UART, etc...)

```python

mydevice = Device(IP("182.168.1.12"))
```

This assumes that the choice of the wrapper is trivial for the user.
