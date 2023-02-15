# Notes

## Communication protocol to use

- Raw data over TCP/IP
  - Allows for more complex commands
  - Multiple commands in one frame
- Ethercat
  - Costly (cheapest IC starts at ~ 10 USD)
  - Need Npcap to run on Windows (at least)
- Modbus TCP
  - Simple
  - Register by register
  - Possibility to describe the function with a json file


### Chosen option (05.06.2022)

Raw data over TCP/IP Because the "make this at time T" option requires more arguments than what Modbus TCP can offer

The byte order through network is always big endian (RFC1700)

## Frames specifications

- Simple commands
  - SPI Write
  - SPI Read
  - Register write / read
- Timed commands
  - Make a command at a specified time
- Interrupt ?
  - The device sends a packet to the host directly (requires a server on the host)
  - Could also be an answer-based system. The host requests the device to send an answer when an event occurs or when the event timeouts


The last 4 bits are configuration for each command (to select between multiple SPIs for example)

### Low-level command management
14.08.2022

When a command is received, it is stored in a buffer locally. Then parsed to extract the necessary values, arrays, etc... (each one is stored in a corresponding variable)

Only one command per frame, otherwise it's going to be unnecessarily difficult to manage them

### Required frames

- SPI read / write with SPI index (0-7). 8 SPI interfaces possible.
- Register read / write with index (0-15) for I/O. 16xN bits with N the number of bits for the registers. 8, 16 or 32 bits specific to each device
- Discover frame (UDP Broadcast)
- I2C read / write with I2C index (0-7). 8 I2C interfaces possible.
- UART read / write with I2C index (0-7). 8 UART interfaces possible.


## Usage

device open function : find device on network and auto-assign driver. If the driver cannot be found, the user is asked to assign one manually


## No controller branch (24.08.2022)

The controllers have been removed. Instead the Network class inherits from controller intefaces (IIPController, IUARTController, etc...)

The methods that need to be implemented by the user are pure virtual and are implemented by the user as if it was the .cpp file
The methods that need to be called by user are implemented in the Network class



## Remark (05.09.2022)

If Ethernet is used as the primary protocol of communication with the devices, it may not work in many schools because of security reasons. Sometimes creating a secondary network on a computer connected to the network is prohibited. A USB to Ethernet bridge could be used to correct this issue (without it being a true Ethernet adapter)
