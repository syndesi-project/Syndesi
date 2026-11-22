Reference
=========

The complete API, generated from the source code, plus the command line tools and the
default values.

Everything listed here can be imported from ``syndesi`` directly
(``from syndesi import IP, Modbus, Termination``), unless a module is given.

.. grid:: 1 2 3 3
   :gutter: 2

   .. grid-item-card:: Adapters
      :link: adapters
      :link-type: doc

      ``IP``, ``SerialPort``, ``Visa``, ``IPServer``

   .. grid-item-card:: Stop conditions
      :link: stop-conditions
      :link-type: doc

      ``Termination``, ``Length``, ``Continuation``, ``Total``, ``FragmentSC``

   .. grid-item-card:: Protocols
      :link: protocols
      :link-type: doc

      ``Delimited``, ``SCPI``, ``Raw``

   .. grid-item-card:: Modbus
      :link: modbus
      :link-type: doc

      ``Modbus``, ``ModbusServer``, ``ModbusMultiRegisterValue``

   .. grid-item-card:: Drivers
      :link: drivers
      :link-type: doc

      ``Driver``, ``SubDriver``, ``SCPIDriver``

   .. grid-item-card:: Bridges
      :link: bridges
      :link-type: doc

      ``I2C``, ``SPI``, ``I2CBridge``, ``SPIBridge``, ``SerialBridge``

   .. grid-item-card:: Events
      :link: events
      :link-type: doc

      What ``register_event_callback`` receives

   .. grid-item-card:: Errors
      :link: errors
      :link-type: doc

      ``SyndesiError`` and its subclasses

   .. grid-item-card:: Command line
      :link: cli
      :link-type: doc

      ``syndesi term``, ``syndesi ui``, ``syndesi-trace``

   .. grid-item-card:: Defaults
      :link: defaults
      :link-type: doc

      Timeouts, stop conditions and ports, at a glance
