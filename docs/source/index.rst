:sd_hide_title:

.. meta::
   :description: Syndesi, a Python library to talk to instruments and devices over IP, serial, VISA, Modbus, SCPI, I2C and SPI

Syndesi
=======

.. raw:: html

   <section class="sy-hero">
     <p class="sy-hero-title">Talk to any device,<br><span class="sy-gradient">in a few lines of Python.</span></p>
     <p class="sy-hero-lead">
       Syndesi gives every instrument, PLC, board and sensor the same simple interface:
       <code>write</code>, <code>read</code>, <code>query</code>.
       Over TCP, UDP, serial, VISA, Modbus, SCPI, I2C or SPI, sync or async.
     </p>
     <div class="sy-hero-actions">
       <a class="sy-btn sy-btn-primary" href="tutorials/first-connection.html">Get started →</a>
       <a class="sy-btn" href="tour.html">Take the tour</a>
       <a class="sy-btn" href="reference/index.html">API reference</a>
     </div>
     <span class="sy-install">pip install syndesi</span>
   </section>

.. code-block:: python

   from syndesi import IP, SCPI

   scope = SCPI(IP("192.168.1.42"))      # port 5025, "\n" termination: SCPI knows its defaults
   print(scope.query("*IDN?"))           # 'KEYSIGHT,DSOX1204G,CN6...,2.12'

Three layers, pick the one you need
-----------------------------------

Every Syndesi object belongs to one of three layers. You can work at any of them, and
stack them like building blocks.

.. raw:: html

   <div class="sy-stack">
     <div class="sy-layer sy-driver">
       <span class="sy-layer-name">Driver</span>
       <span class="sy-layer-items">psu.set_voltage(3.3) · mm.measure_dc_voltage()</span>
       <span class="sy-layer-type">your methods</span>
     </div>
     <div class="sy-layer sy-protocol">
       <span class="sy-layer-name">Protocol</span>
       <span class="sy-layer-items">Delimited · SCPI · Modbus · Raw</span>
       <span class="sy-layer-type">str, registers…</span>
     </div>
     <div class="sy-layer sy-adapter">
       <span class="sy-layer-name">Adapter</span>
       <span class="sy-layer-items">IP · SerialPort · Visa · IPServer · I2C · SPI</span>
       <span class="sy-layer-type">bytes</span>
     </div>
     <div class="sy-device">▼ YOUR DEVICE</div>
   </div>

.. grid:: 1 1 3 3
   :gutter: 3

   .. grid-item-card:: Adapters
      :link: how-to/connect
      :link-type: doc

      Move bytes over TCP, UDP, serial ports and VISA. Stop conditions decide where
      each message ends.

   .. grid-item-card:: Protocols
      :link: how-to/text-commands
      :link-type: doc

      Text commands, SCPI instruments, Modbus TCP/RTU/ASCII client **and** server.

   .. grid-item-card:: Drivers
      :link: how-to/write-a-driver
      :link-type: doc

      Wrap a device in a class with meaningful methods, then reuse it everywhere.

Find your way
-------------

The documentation is organized in four parts, each with its own purpose.

.. grid:: 1 1 2 2
   :gutter: 3

   .. grid-item-card:: 🎓 Tutorials
      :link: tutorials/index
      :link-type: doc
      :class-card: sy-section-card

      **Learning.** Follow along from your first ``query()`` to your own driver and a
      Modbus device, no hardware required.

   .. grid-item-card:: 🧭 How-to guides
      :link: how-to/index
      :link-type: doc
      :class-card: sy-section-card

      **Solving.** Short recipes for a precise goal: open a serial port, read a float
      from a PLC, debug a timeout…

   .. grid-item-card:: 💡 Concepts
      :link: explanation/index
      :link-type: doc
      :class-card: sy-section-card

      **Understanding.** How the layers fit, how a message is framed, why sync and
      async share the same engine.

   .. grid-item-card:: 📖 Reference
      :link: reference/index
      :link-type: doc
      :class-card: sy-section-card

      **Looking up.** Every class and method, command line tools, default values.

Batteries included
------------------

.. grid:: 1 2 3 3
   :gutter: 2

   .. grid-item::

      **⚡ Sync and async**

      Every adapter and protocol exists as ``IP`` / ``AsyncIP``, ``Modbus`` /
      ``AsyncModbus``…, same API.

   .. grid-item::

      **🧩 Smart defaults**

      Protocols set the port, termination and timeout they need. You only write what
      differs.

   .. grid-item::

      **🔍 Live trace**

      Run ``syndesi-trace`` and watch every byte your scripts exchange, in real time.

   .. grid-item::

      **🖥️ Terminal**

      ``syndesi term serial /dev/ttyUSB0 115200``: an interactive console for any
      device.

   .. grid-item::

      **🪟 Graphical bench**

      ``syndesi ui``: stack layers, call methods and inspect traffic without writing
      code.

   .. grid-item::

      **🔌 Bridges**

      Expose the I2C, SPI or UART of a custom board as standard Syndesi objects.

.. toctree::
   :hidden:

   Home <self>
   tour

.. toctree::
   :hidden:
   :caption: Tutorials

   tutorials/index
   tutorials/first-connection
   tutorials/scpi-instrument
   tutorials/first-driver
   tutorials/modbus-loopback

.. toctree::
   :hidden:
   :caption: How-to guides

   how-to/index
   how-to/connect
   how-to/framing
   how-to/text-commands
   how-to/scpi
   how-to/modbus-client
   how-to/modbus-server
   how-to/ip-server
   how-to/async
   how-to/write-a-driver
   how-to/bridges
   how-to/hid
   how-to/errors
   how-to/debugging
   how-to/terminal
   how-to/gui

.. toctree::
   :hidden:
   :caption: Concepts

   explanation/index
   explanation/layers
   explanation/frames
   explanation/engine

.. toctree::
   :hidden:
   :caption: Reference

   reference/index
   reference/adapters
   reference/stop-conditions
   reference/protocols
   reference/modbus
   reference/drivers
   reference/bridges
   reference/events
   reference/errors
   reference/cli
   reference/defaults
