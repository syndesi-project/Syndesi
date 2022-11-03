# Install Guide

## Installation with Arduino

- Option 1 : Download the syndesi.zip archive from releases and install it via the Arduino IDE
- Option 2 : Clone the repository and run ``./install_arduino_library.sh``
  
The Syndesi library will be available with #include<syndesi>. Some Arduino examples are also provided

## Installation with cmake

The library must be compiled from source each time. This is due to the file ``syndesi_config.h`` which configures the main functionnalities of the library.

To add the library, do the following :

```cmake
# Include the files
include_directories(<path_to_include_folder>)
file(GLOB syndesi_sources CONFIGURE_DEPENDS <path_to_src_folder>/*.cpp)
file(GLOB syndesi_header CONFIGURE_DEPENDS <path_to_include_folder>/*.h)

add_library(syndesi ${syndesi_sources} ${syndesi_header})

# The syndesi_config.h file can be placed anywhere
target_include_directories(syndesi PUBLIC <path_to_syndesi_config_file>)

target_link_library(<your_target> syndesi)
```

In a nutshell, everything that's need for the library to be usable is :

- The source files ``src/*.cpp``
- The header files ``include/*.h``
- The configuration file ``user_config/syndesi_config.h``