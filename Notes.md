# Syndesi C++ library

## Notes 29.04.2023

Add a "Serial finder" protocol that is able to find a serial port even if it has changed name (it basically exludes all of the others specified in a blacklist and looks for the remaining one)

## Notes 15.08.2022

The payload manager is probably not going to be used, each class below includes the class above.


## Notes 16.08.2022

Buffer problem : when we get a frame from the IP stack, we know its size and we can allocate accordingly

When we create the reply, we do not know any clean way to create the right buffer size when building the payload (and then adding the size, the command, the sdid etc...)

The solution is to ask the Buffer to tell us what's the offset of the subbuffer, then we can create a new buffer with the payload size + the offset (since the reply frame will have exactly the same header length, including sdid(s))


## Notes 06.05.2023

The new structure is a follows : Any communication between a host and a device happens through at least three layers

- adapter : the low-level implementation of the physical/network layers, like IP, Serial, etc...
- protocol : Implementation of the transport up to application layers, like Profinet, SDP, SCPI, Telnet, Modbus, HTTP or Raw
- driver(s) : Device specific or application specific (testbenches) classes, these classe can be user-defined and may contain information on how a particular device works. In the case of a testbench driver, multiple devices (drivers) can be passed as arguments to run the testbench

## Notes 28.05.2023

The Syndesi and Syndesi-drivers packages should not overlap (i.e provide the same syndesi module) as this will cause problems. It's better for each to provide its own module (syndesi and syndesi_drivers for example)

## Notes 02.06.2023

The protocol is specified by the device itself, if multiple protocols are available for a particular device, a method is implemented to choose (or take a default one)

## Notes 18.07.2023

new-structure and sync branches are considered close, development will continue on main

## 16.08.2023

Syndesi ressembles a prime factor decomposition, it aims to decompose a multitude of tasks into their fundamental base elements, some of which could be made with Syndesi.