See what is going on
====================

Watch the traffic live
----------------------

Every Syndesi adapter publishes what it does on a local channel. Open a second terminal
and run:

.. code-block:: console

   $ syndesi-trace

Then run your script as usual: each adapter gets its own tab, with every write, every
fragment received, and the stop condition that ended each frame. Nothing to change in
your code.

.. code-block:: console

   $ syndesi-trace --flat                    # one line per event, no tabs
   $ syndesi-trace --filter "192.168.1.*"    # only some adapters
   $ syndesi-trace --time abs                # absolute timestamps
   $ syndesi-trace --no-frag                 # hide fragments, frames only
   $ syndesi-trace --flat --output trace.log # save to a file

Give your adapters an ``alias`` to recognize them easily.

Inspect a frame
---------------

The ``_detailed`` methods return the frame with its timing:

.. code-block:: python

   >>> frame = dev.query_detailed(b"*IDN?\n")
   >>> frame.data
   b'ACME,PSU-3000,1234,1.0\n'
   >>> frame.response_delay          # write → first byte, in seconds
   0.0021
   >>> frame.stop_condition          # what ended the frame
   Continuation(0.200)

A ``Continuation`` where you expected a ``Termination`` usually means the terminator
is wrong.

React to events in your code
----------------------------

.. code-block:: python

   from syndesi.adapters.events import (
       AdapterClosedEvent,
       AdapterFrameEvent,
       AdapterWriteEvent,
   )

   def on_event(event):
       if isinstance(event, AdapterWriteEvent):
           print("→", event.frame.data)
       elif isinstance(event, AdapterFrameEvent):
           print("←", event.frame.data)
       elif isinstance(event, AdapterClosedEvent):
           print("closed")

   dev.register_event_callback(on_event)

Callbacks run on Syndesi's internal thread: keep them short and never call the adapter
from inside one. See :doc:`/reference/events` for every event.

Turn on logging
---------------

Syndesi logs through the standard ``logging`` module, under the ``syndesi`` logger:

.. code-block:: python

   import logging

   logging.basicConfig(level=logging.INFO)
   logging.getLogger("syndesi").setLevel(logging.DEBUG)

Sub-loggers: ``syndesi.adapter``, ``syndesi.protocol``, ``syndesi.engine``,
``syndesi.framer``, ``syndesi.reactor``.

Try commands by hand
--------------------

Before writing code, check that the device answers with :doc:`terminal`:

.. code-block:: console

   $ syndesi term ip 192.168.1.10 5025
