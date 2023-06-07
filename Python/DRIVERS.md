# Syndesi Drivers

Each device driver has its own class. By default each file contains a single class, but multiple can be declared if it suits the application

The driver is the top-level module instanciated by the user for each device.
To instanciate a device, the user provides a identifier either as a string (that will be automatically detected) or as a specified class

```python
from syndesi.drivers.xxx.DeviceX

# From a string (IPv4)
myDevice = DeviceX("192.168.1.12") # not implemented yet
# From a class (IPv4)
myDevice = DeviceX(IP("192.168.1.12"))
# From a class (usb VID/PID)
myDevice = DeviceX(USB(0xFE41, 0x1234))
```

## Meta-drivers

Meta-drivers are optional interface classes to provide basic functionnality like
voltmeter DC/AC read, multimeter resistance measurement, etc...

Meta-drivers can be used to create generic testbenches, not linked to a particular device

## Categories

- ``instruments`` : bench/lab equipement like voltmeters, oscilloscopes, etc..
  - ``powersupplies``
  - ``multimeters``
  - ``oscilloscopes``
  - ``waveformGenerators``
  - ``electronicLoads``
- ``picoscope`` : Support for picoscope drivers
- ``raw`` : Raw drivers (serial port, raw TCP, etc..)

## Adding a missing method

If a testbench requires a custom method that is missing from the driver implementation, it can be added by doing the following

```python
from syndesi.drivers.xxx.xxx import Device

def newMethod(self, optionalArgs):
    # Implementation here

Device.newMethod = newMethod

## OR

Device.newMethod = lambda self : # implementation here
```

## Notes / FAQ

1) *Why use the driver as the main instance for the device ?* This approach allows for the interpreter to know in advance what the type is going to be and provide the necessary auto-completion. It also allows the driver to know what type of communication is used and adapt the protocol is necessary. The trade-off is that a Syndesi driver cannot be reused on other projects without significant modifications.