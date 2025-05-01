Usage
-----

To open a communication with a device, simply instantiate one of the following :

* **Adapter** : Manage only low-level communication with the device (byte arrays)
    * **IP**
    * **SerialPort**
    * **VISA**
* **Protocol** : Send data using dedicated protocol.
    * **Raw**, no protocol
    * **Delimited**, text based commands ended by a delimiter character ('\n' by default)
    * **SCPI**, text based commands for use with test instruments
    * **Modbus**, modbus implementation (Comaptible with SerialPort and IP)
* **Driver** : Use high-level device-specific function (like ``read_voltage`` for a multimeter). Those can be user-defined or loaded from the syndesi-drivers library

Example of device instantiation using low-level Adapter class::

    from syndesi.adapters import IP

    my_device = IP('192.168.1.26') # Instanciate the device, TCP by default

    id = my_device.query('*IDN?\n') # Query its identification string (SCPI IDN command)

Protocol example::

    from syndesi.protocols import Delimited
    from syndesi.adapters import IP

    my_device = Delimited(IP('10.0.0.5'), termination='\n')

    data = my_device.query('READ?')
    # b'1.23194e1'

Driver example::

    from syndesi_drivers.instruments.multimeters.siglent import SDM3055

    mm = SDM3055(IP('10.0.1.2'))

    voltage = mm.measure_dc_voltage()
    # 12.19671

