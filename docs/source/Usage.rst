Usage
-----

To open initiate a communication with a device, simply instantiate one of the following :

* **Adapter** : Manage only low-level communication with the device (byte arrays). Those include :
    * **IP**
    * **SerialPort**
    * **VISA**
* **Protocol** : Send data using dedicated protocol. Those include :
    * **Raw**, no protocol
    * **Delimited**, text based commands ended by a delimiter character ('\n' by default)
    * **SCPI**, text based commands for use with test instruments
    * **Modbus**, modbus implementation (Comaptible with SerialPort and IP)
* **Driver** : Use high-level device-specific function (like ``read_voltage`` for a multimeter). Those can be user-defined or loaded from the syndesi-drivers library

Example of device instantiation using low-level Adapter class::

    from syndesi.adapters import IP

    my_device = IP('192.168.1.26') # Instanciate the device, TCP by default

    my_device.query('*IDN?\n') # Query its identification string (SCPI IDN command)
    id = my_device.read() # Get device identification ()

