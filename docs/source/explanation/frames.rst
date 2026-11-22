Frames and timeouts
===================

You send a question, the device answers ``b"21.5\n"``. Simple. But the wire carries no
such thing as "an answer": it carries bytes, and the system hands them over in pieces
of arbitrary size. This page explains how Syndesi turns those pieces back into
answers.

Fragments and frames
--------------------

Each piece of data the system delivers is a **fragment**. The answer you expect is a
**frame**. A frame can come in one fragment, or in several:

.. code-block:: text

   time ─────────────────────────────────────────────────────►
   fragments    b"21"   b".5"       b"\n"  b"OK\n"
   frames       └──── b"21.5\n" ────┘      └ b"OK\n" ┘

and one fragment can contain several frames, or the end of one and the start of the
next. Cutting the flow of fragments into frames is the job of the adapter's
**framer**, guided by **stop conditions**.

Stop conditions
---------------

A stop condition looks at the fragments as they arrive and decides when the current
frame is complete:

=====================  ======================================================
``Termination(seq)``   when ``seq`` is received (``b"\n"``, ``b"\r\n"``…)
``Length(n)``          when ``n`` bytes are received
``Continuation(t)``    when nothing new arrived for ``t`` seconds
``Total(t)``           ``t`` seconds after the first byte of the frame
``FragmentSC()``       at every fragment
=====================  ======================================================

``Termination`` and ``Length`` look at the data, ``Continuation`` and ``Total`` at the
clock. When a condition ends a frame in the middle of a fragment, the rest is not lost:
it starts the next frame.

Every adapter starts with a ``Continuation``, because it works with any device without
knowing anything about it: an answer is over when the device stops talking. It costs a
little time on every read (the length of the silence), which is why a ``Termination``,
when the device has a terminator, is faster.

Protocols choose the stop conditions they need: ``Delimited`` and ``SCPI`` use a
``Termination``, Modbus TCP reads the length from its header, Modbus RTU detects the
silence between frames.

The read buffer
---------------

Frames don't wait for you to call ``read()``. As soon as one is complete, it goes into
the adapter's buffer, along with its timestamps. A ``read()`` then takes a frame from
it:

- ``read()`` returns the oldest buffered frame, even if it arrived before the call
  (scope ``"buffered"``);
- ``read(scope="next")`` ignores what is buffered and waits for a new frame;
- ``query()`` writes, then returns the first frame received *after* that write (scope
  ``"last_write"``). Leftovers from earlier exchanges can't be mistaken for the answer.

``clear_read_buffer()`` empties the buffer.

Each frame records how it was built: ``read_detailed()`` and ``query_detailed()``
return it with ``stop_condition`` (what ended it) and ``response_delay`` (time between
the write and its first byte).

.. _timeouts:

Timeouts
--------

A **timeout** limits how long a read waits for an answer. Without one, a device that
never answers would block your program forever. When it expires, the read raises
``AdapterTimeoutError``. A frame arriving later goes to the buffer, like any other.

Every adapter waits 2 s by default. You can change it at three levels:

.. code-block:: python

   dev = IP("192.168.1.10", 5025, timeout=10)   # for every read
   dev.set_timeout(3)                            # from now on
   dev.query(b"MEAS?\n", timeout=30)             # for this call only

``timeout=None`` waits without limit.

With a protocol
^^^^^^^^^^^^^^^

A protocol has a timeout too, and **gives it to its adapter**: ``SCPI(IP(...))`` waits
5 s, the SCPI default, not the 2 s of ``IP``. Set it on the protocol, the adapter
follows:

.. code-block:: python

   scope = SCPI(IP("192.168.1.42"), timeout=10)   # 10 s for every query
   scope.set_timeout(20)                          # from now on
   scope.query("MEAS?", timeout=30)               # for this call only

Each layer still has its own timeout, and you may choose both. The adapter waits for
the first bytes of the answer, the protocol for the complete message:

.. code-block:: python

   # Fail fast if the instrument is silent, but give a long answer time to arrive
   scope = SCPI(IP("192.168.1.42", timeout=1), timeout=10)

Who decides, from the strongest to the weakest:

1. A timeout given to the call, ``query(..., timeout=30)``: it covers the whole
   exchange.
2. A timeout **you** gave the adapter, at its creation or with ``set_timeout``. No
   driver or protocol overrides it.
3. The timeout of the protocol, given or default.
4. A default set by a driver with ``set_default_timeout``, adopted by the protocol it
   builds when that protocol isn't given one.
5. The default of the adapter.

When a frame is incomplete
^^^^^^^^^^^^^^^^^^^^^^^^^^

A timeout says what arrived. If bytes came but never formed a valid frame, the
message shows them, and what the frame was waiting for:

.. code-block:: text

   AdapterTimeoutError: No valid frame received within 2.0 seconds, but already
   received b'OK\r' (3 bytes), waiting for Termination(b'\n')

Here the device ends its answers with ``\r`` while ``\n`` is expected. The bytes are
in ``error.received``.
