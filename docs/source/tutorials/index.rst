Tutorials
=========

Hands-on lessons, to read in order. Each one takes about ten minutes and runs on your
computer alone: the "devices" are small scripts that pretend to be one.

.. grid:: 1 1 2 2
   :gutter: 3

   .. grid-item-card:: 1 · Your first connection
      :link: first-connection
      :link-type: doc

      Install Syndesi, talk to an echo server, discover ``write``, ``read`` and
      ``query``.

   .. grid-item-card:: 2 · Control an instrument with SCPI
      :link: scpi-instrument
      :link-type: doc

      Drive a (simulated) lab power supply: set a voltage, switch the output on,
      measure.

   .. grid-item-card:: 3 · Write your first driver
      :link: first-driver
      :link-type: doc

      Turn those SCPI strings into a ``PowerSupply`` class with real methods, then
      open it in the graphical bench.

   .. grid-item-card:: 4 · A Modbus device in five minutes
      :link: modbus-loopback
      :link-type: doc

      Create a Modbus TCP server, then read and write its registers like a PLC.

.. tip::

   Already comfortable with Python and instruments? Skim the :doc:`/tour`, then jump to
   the :doc:`/how-to/index`.
