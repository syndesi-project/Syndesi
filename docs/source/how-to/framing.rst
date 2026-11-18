Decide where a message ends
===========================

Bytes arrive in pieces. **Stop conditions** tell the adapter when the pieces form a
complete message (a *frame*). Pass one, or a list, as ``stop_conditions``.

.. seealso::

   :doc:`/explanation/frames` explains how fragments become frames.

Stop on a terminator
--------------------

The most common case: each message ends with ``\n``, ``\r\n``, ``>``…

.. code-block:: python

   from syndesi import SerialPort, Termination

   port = SerialPort("/dev/ttyUSB0", 115200, stop_conditions=Termination(b"\r\n"))

The terminator stays in the returned data. Use :doc:`Delimited <text-commands>` to have
it removed (and added on writes) for you.

Read a fixed number of bytes
----------------------------

.. code-block:: python

   from syndesi import IP, Length

   dev = IP("10.0.0.7", 4000, stop_conditions=Length(16))
   header = dev.read()   # exactly 16 bytes

Extra bytes are not lost: they start the next frame.

Stop when the line goes quiet
-----------------------------

``Continuation`` ends the frame when nothing arrived for a given time. It is the
default for every adapter (200 ms for ``IP``, 100 ms for ``SerialPort`` and ``Visa``),
because it works with any device. Make it shorter to get answers faster:

.. code-block:: python

   from syndesi import Continuation, SerialPort

   port = SerialPort("/dev/ttyACM0", 115200, stop_conditions=Continuation(0.02))

Cap the duration of a frame
---------------------------

``Total`` ends the frame a given time after its first byte, whatever happens. Useful for
devices that stream continuously:

.. code-block:: python

   from syndesi import IP, Total

   stream = IP("192.168.1.80", 7000, stop_conditions=Total(0.5))
   chunk = stream.read()   # everything received in 0.5 s

Combine conditions
------------------

With a list, the frame ends as soon as one of them triggers. A terminator with a safety
net, in case the terminator is lost:

.. code-block:: python

   from syndesi import IP, Termination, Total

   dev = IP("192.168.1.10", 4000, stop_conditions=[Termination(b"\n"), Total(2.0)])

Conditions are checked in the order of the list.

Get every piece as it comes
---------------------------

``FragmentSC`` makes each chunk received from the system a frame of its own, with no
assembly:

.. code-block:: python

   from syndesi import FragmentSC, SerialPort

   sniffer = SerialPort("/dev/ttyUSB1", 9600, stop_conditions=FragmentSC())

Find out which condition ended a frame
--------------------------------------

The ``_detailed`` variants return the frame with its metadata:

.. code-block:: python

   >>> frame = dev.query_detailed(b"PING\n")
   >>> frame.data
   b'PONG\n'
   >>> frame.stop_condition
   Termination(b'\n')
   >>> frame.response_delay      # seconds between the write and the first byte
   0.0012

Change conditions on the fly
----------------------------

.. code-block:: python

   dev.set_stop_conditions(Length(4))

Read what came before, or only what comes next
----------------------------------------------

By default ``read()`` returns the oldest frame waiting in the buffer. ``scope`` changes
that:

.. code-block:: python

   dev.read(scope="buffered")    # default: the oldest frame, even if it arrived earlier
   dev.read(scope="next")        # only a frame that starts after this call
   dev.clear_read_buffer()       # forget everything received so far

``query()`` always returns the frame received after its own write.
