How-to guides
=============

Short recipes for a precise goal. They assume you know the basics from the
:doc:`/tutorials/index`.

.. grid:: 1 1 2 2
   :gutter: 3

   .. grid-item-card:: Connect to a device
      :link: connect
      :link-type: doc

      TCP, UDP, serial ports, VISA, descriptor strings, port discovery.

   .. grid-item-card:: Decide where a message ends
      :link: framing
      :link-type: doc

      Terminators, fixed lengths, silences and time limits.

   .. grid-item-card:: Send text commands
      :link: text-commands
      :link-type: doc

      ``Delimited`` for line-based devices, ``Raw`` for binary ones.

   .. grid-item-card:: Control SCPI instruments
      :link: scpi
      :link-type: doc

      Power supplies, multimeters, scopes, over LAN, USB or GPIB.

   .. grid-item-card:: Read and write a Modbus device
      :link: modbus-client
      :link-type: doc

      Modbus TCP, RTU and ASCII: registers, coils, floats, strings.

   .. grid-item-card:: Simulate a Modbus device
      :link: modbus-server
      :link-type: doc

      A Modbus server with its data tables and custom handlers.

   .. grid-item-card:: Accept TCP connections
      :link: ip-server
      :link-type: doc

      ``IPServer``: each client becomes an adapter.

   .. grid-item-card:: Use async / await
      :link: async
      :link-type: doc

      The async twin of every adapter and protocol.

   .. grid-item-card:: Write a driver
      :link: write-a-driver
      :link-type: doc

      Wrap a device in a class, split it into sub-drivers, accept any adapter.

   .. grid-item-card:: Reach I2C, SPI and UART through a board
      :link: bridges
      :link-type: doc

      Bridges: expose the buses of a custom board as Syndesi objects.

   .. grid-item-card:: Handle errors and timeouts
      :link: errors
      :link-type: doc

      What to catch, and when.

   .. grid-item-card:: See what is going on
      :link: debugging
      :link-type: doc

      ``syndesi-trace``, events, logging, frame details.

   .. grid-item-card:: Use the interactive terminal
      :link: terminal
      :link-type: doc

      ``syndesi term``: talk to a device by hand.

   .. grid-item-card:: Use the graphical bench
      :link: gui
      :link-type: doc

      ``syndesi ui``: assemble layers and call methods with no code.
