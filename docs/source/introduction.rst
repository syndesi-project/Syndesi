Introduction
============

Syndesi is a Python package designed to facilitate reliable communication with hardware devices.

Syndesi is particulary well suited for testbench creation and is aimed at engineers, hobbyists, and educators, providing a unified interface for various connection types (IP, SerialPort, VISA) and data formatting protocols (Delimited, SCPI, Modbus).

**Main Features:**

- Simple interface for establishing connections
- Support for multiple communication protocols
- Extensible design for adding new protocols or device-specific drivers

**Installation**

To install Syndesi, use the following:

.. code-block:: bash
    pip install syndesi

**Quickstart Example:**

.. code-block:: python
    
    # Send a command to a device and read a response
    from syndesi import IP

    protocol = IP("192.168.1.10", port=5025)
    response = protocol.query("COMMAND\n")
    print(response)


Refer to the Adapters and Protocols sections for more details on configuring specific settings.

Depending on the application, the user can select the most approriate layer

- Adapter (low-level)
- Protocol
- Driver (high-level)


.. image:: ../diagrams/layers.svg
