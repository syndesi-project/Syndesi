# Syndesi

The Syndesi library is engineered to streamline communication between computers and diverse devices capable of interfacing via standard communication protocols.
This encompasses a broad spectrum of devices, ranging from laboratory instruments to industrial sensors and robotic systems. This is achieved through a 3-level class system :

- Adapter class : low-level communication with a device, timeout management
- Protocol class : high-level, protocol specific implementations for ModBus, HTML, SCPI, etc...


## Applications

- Testbenches, communication with lab instruments (multimeters, oscilloscopes, power supplies, etc...)
- Communication with UART-based devices (Arduino projects, sensors, instruments)
