Protocols
=========

Protocols give messages their shape, on top of an adapter. Guides:
:doc:`/how-to/text-commands`, :doc:`/how-to/scpi`. Modbus has :doc:`its own page
<modbus>`.

Common methods
--------------

.. autoclass:: syndesi.protocols.protocol.Protocol
   :members: open, close, write, write_raw, read, read_detailed, query, query_detailed,
             set_timeout, clear_buffer, is_open, timeout, register_event_callback,
             clear_event_callbacks
   :no-show-inheritance:

.. autoclass:: syndesi.protocols.protocol.ProtocolFrame
   :members:
   :undoc-members:
   :no-show-inheritance:

Text
----

.. autoclass:: syndesi.protocols.delimited.Delimited
   :members: termination, receive_termination, set_termination
   :no-show-inheritance:

.. autoclass:: syndesi.protocols.scpi.SCPI
   :members: termination, write_raw
   :no-show-inheritance:

Binary
------

.. autoclass:: syndesi.protocols.raw.Raw
   :no-members:
   :no-show-inheritance:

Async variants
--------------

.. autoclass:: syndesi.protocols.delimited.AsyncDelimited
   :no-members:
   :no-show-inheritance:

.. autoclass:: syndesi.protocols.scpi.AsyncSCPI
   :no-members:
   :no-show-inheritance:

.. autoclass:: syndesi.protocols.raw.AsyncRaw
   :no-members:
   :no-show-inheritance:
