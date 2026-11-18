Send text commands
==================

Line-based devices: ``Delimited``
---------------------------------

Most microcontroller firmwares, sensors and test fixtures exchange lines of text.
``Delimited`` adds the terminator on writes, cuts and strips it on reads, and works
with ``str``:

.. code-block:: python

   from syndesi import Delimited, SerialPort

   board = Delimited(SerialPort("/dev/ttyUSB0", 115200))
   board.write("led on")
   board.query("temp?")      # '21.5'

Another terminator
------------------

.. code-block:: python

   Delimited(adapter, "\r\n")      # CR LF, both ways
   Delimited(adapter, "\r")        # CR

When the device answers with a different terminator than the one it expects:

.. code-block:: python

   Delimited(adapter, termination="\r", receive_termination="\r\n")

Keep the terminator in the answers
----------------------------------

.. code-block:: python

   Delimited(adapter, format_response=False).query("temp?")   # '21.5\n'

Another encoding
----------------

.. code-block:: python

   Delimited(adapter, encoding="latin-1")

Binary devices: ``Raw``
-----------------------

``Raw`` passes bytes through untouched. It is the base to build your own binary
protocol in a driver, while keeping the adapter's stop conditions:

.. code-block:: python

   from syndesi import IP, Length, Raw

   dev = Raw(IP("10.0.0.7", 4000, stop_conditions=Length(8)))
   dev.query(b"\xaa\x01\x00\x00")

Send bytes through a text protocol
----------------------------------

``write_raw`` skips encoding, for the odd binary command:

.. code-block:: python

   board.write_raw(b"\x1b")    # ESC, no terminator added
