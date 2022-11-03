# Syndesi

The Syndesi library implements low-level communication between syndesi compatible devices (layers 5 and 6 of the OSI model) as well as host-specific high level functions to manage devices

The Syndesi Communication Protocol is responsible for the following tasks :

- Managing communication ports (Ethernet, I²C, SPI, RS-485, etc...)
- Routing frames through and/or between those communication ports
- Managing inbound / outbound frames and their corresponding actions


The installation instructions are found ![here](INSTALL.md)


## Usage

To use the library, the user needs to :

### 1) Edit the configuration file

The file is located is located at ``user_config/syndesi_config.h``

The **mode** must be set :

- host : Syndesi Master (like a computer)
- device : Syndesi subordinate (like an I/O interface)

### 2) Include the files

The configuration file must be included before the library

```c++
#include "syndesi_config.h"
#include <syndesi>
```

This is done so that the #define in the configuration file are passed to the library

### 3) Declare controllers

A controller is child class of syndesi::SAP::IController. The user must create this class and implement all of its virtual functions.

```c++
class MyController :: syndesi::SAP::IController {
    // User code
}
```

Then the controller must be instanciated and added to the network class

```c++
myController = MyController();
core.addController(myController);
```


### 4) Implement command specific callbacks

There are two types of callbacks :

- Request : function called on the device whenever a request is received from the host
- Reply : function called on the host whenever a device sends data back

## FAQ

Why is the library headers only ? It seems like the only solution to be able to :

- Configure the library with ``syndesi_config.h`` file
- Not having this file inside the library (and having the same config for all projects)
- Be able to use the library with the Arduino IDE (so no ``__has_include`` possible)
- Being able to #ifdef the callbacks (no runtime finding the right one or instianciation of all of them)