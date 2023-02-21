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


## Notes (obsolete)
The user could specify the wrapper directly (IP, UART, etc...)

```python

mydevice = Device(IP("182.168.1.12"))
```

This assumes that the choice of the wrapper is trivial for the user.
