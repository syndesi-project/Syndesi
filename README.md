# Syndesi

The Syndesi library implements low-level communication between syndesi compatible devices (layers 5 and 6 of the OSI model) as well as host-specific high level functions to manage devices

The Syndesi library is responsible for :

- Managing communication ports (Ethernet, I²C, SPI, RS-485, etc...)
- Routing frames through and/or between those communication ports
- Managing inbound / outbound frames and their corresponding actions


The installation instructions are found ![here](INSTALL.md)

## Usage

To use the library, the user needs to :

### 1) Edit the configuration file

The file is located is located at ``user_config/syndesi_config.h``

#### Mode

- host : Syndesi Master (like a computer)
- device : Syndesi subordinate (like an I/O interface)

#### Controller

A controller allows the syndesi library to communicate through a specific interface (Ethernet, I²C, SPI, etc...)

If necessary, the user can provide a custom implementation of a controller

### 2) Include the files

The configuration file must be included before the library, if the configuration file is in an include folder, the syndesi library will include it automatically (through ``__has_include``). Otherwise it can be included by the user manually beforehand

```c++
#include "syndesi_config.h" // Only necessary if __has_include is unavailable, with Arduino for example
#include <syndesi>
```

This is done so that the #define in the configuration file are passed to the library

### 4) Implement command specific callbacks

There are two types of callbacks :

- Request : function called on the device whenever a request is received from the host
- Reply : function called on the host whenever a device sends data back

Each callback function needs to be implemented by the user and then set accordingly :

```C++
void user_callback(<arguments>) {
    // User code
}

// Initialisation
core.callbacks.<callback> = user_callback
```

the ``<arguments>`` can be found in the command list

## FAQ

Why is some of the source inside headers and the rest inside .cpp files ? This is a compromise to be able to

- Configure the library with ``syndesi_config.h`` file (if the library is used from source)
- Not having the config file inside the library (and having the same config for all projects)
- Be able to use the library with the Arduino IDE (so no ``__has_include`` possible), in that case the ``syndesi_config.h`` is included before the library
- Being able to #ifdef the callbacks (no runtime finding the right one or instianciation of all of them). The shared library has all of the callbacks enabled by default, but compiling the library from source allows the user to configure which ones are enabled (for embedded applications for example)
