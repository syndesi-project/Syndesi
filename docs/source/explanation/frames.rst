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

Each adapter has its own default: 1 s for ``IP``, 2 s for ``SerialPort``, 5 s for
``Visa``. You can change it at three levels:

.. code-block:: python

   dev = IP("192.168.1.10", 5025, timeout=10)   # for every read
   dev.set_timeout(3)                            # from now on
   dev.query(b"MEAS?\n", timeout=30)             # for this call only

``timeout=None`` waits without limit.

When a protocol is stacked on an adapter, both have a timeout, and a read through the
protocol waits for the **shorter** of the two. The simplest rule is to give the timeout
to the adapter when you create it: the protocol then adopts the same value.

.. code-block:: python

   scope = SCPI(IP("192.168.1.42", timeout=10))   # 10 s for every query
