The engine
==========

When you call ``dev.query(...)``, the work doesn't happen in your thread. This page
explains where it happens, and what that gives you.

One thread for every adapter
----------------------------

Syndesi runs a single background thread, the **reactor**. Every adapter and protocol
has an **engine** that lives on it. The reactor watches all their connections at once
(with ``select``), and handles whatever arrives: it reads fragments, runs the stop
conditions, fills the buffers, fires the events, emits the trace.

.. code-block:: text

   your thread          ┌──────────────── reactor thread ────────────────┐
                        │                                                │
   dev.query(b"x") ───► │ engine(IP) ── socket ──► device                │
        waits     ◄──── │   framer ◄── fragments ◄──                     │
                        │   buffer, events, trace                        │
                        │                                                │
   plc.read_coils() ──► │ engine(Modbus) ─► engine(IP) ── socket ──► PLC │
                        └────────────────────────────────────────────────┘

The methods you call submit a command to the engine and wait for its result. Your code
stays simple and blocking, and the reactor never misses data, even while your program
is busy elsewhere.

That's why data received between two reads isn't lost, why timestamps are precise, why
``syndesi-trace`` sees everything, and why a hundred adapters don't need a hundred
threads.

.. note::

   Two transports can't be watched by ``select``: VISA, and serial ports on Windows.
   Their adapters read in a small helper thread that wakes the reactor up, and take the
   timestamps right when the data arrives, so stop conditions stay precise.

Sync and async are the same thing
---------------------------------

The engine is non-blocking: every command returns a future. The only difference
between ``IP`` and ``AsyncIP`` is how they wait for it:

.. code-block:: python

   future.result()                      # IP
   await asyncio.wrap_future(future)    # AsyncIP

Everything else (framing, buffering, timeouts, events) is shared code. ``AsyncIP``
isn't a port of ``IP``, it is the same adapter with a different way of waiting, so
both always behave identically.

Opening on first use
--------------------

Adapters don't connect when they are created, but at the first operation that needs
the device. This leaves time for what is stacked on top to finish configuring them:
``SCPI`` sets port 5025, a driver sets its baudrate, and only then is the connection
opened, with the right settings.

Call ``open()`` explicitly to connect right away (and fail early). Once you've called
``close()``, the adapter stays closed until the next explicit ``open()``.

Callbacks and the reactor
-------------------------

Event callbacks run on the reactor thread. While a callback runs, no other adapter is
served, which is why callbacks must be short, and must never wait for an adapter: the
adapter would wait for the reactor, which waits for the callback.

Bridges have their own thread
-----------------------------

A bridge (see :doc:`/how-to/bridges`) is written as blocking code: it sends a command
to its board and waits for the answer. It can't run on the reactor, which would then
be unable to deliver the answer it waits for. Each bridge gets its own worker thread,
which also serializes its users (several I2C addresses, a serial port…) without any
lock.
