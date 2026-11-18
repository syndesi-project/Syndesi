Events
======

What ``register_event_callback`` receives. Every event has a ``timestamp``
(``time.time()``). Guide: :doc:`/how-to/debugging`.

.. warning::

   Callbacks run on Syndesi's reactor thread. Keep them short, and never call an
   adapter or a protocol from inside one.

Adapter events
--------------

``from syndesi.adapters.events import ...``

.. autoclass:: syndesi.adapters.events.AdapterOpenedEvent
   :no-members:
   :no-show-inheritance:

.. autoclass:: syndesi.adapters.events.AdapterClosedEvent
   :no-members:
   :no-show-inheritance:

.. autoclass:: syndesi.adapters.events.AdapterWriteEvent
   :members:
   :undoc-members:
   :no-show-inheritance:

.. autoclass:: syndesi.adapters.events.AdapterFragmentEvent
   :members:
   :undoc-members:
   :no-show-inheritance:

.. autoclass:: syndesi.adapters.events.AdapterFrameEvent
   :members:
   :undoc-members:
   :no-show-inheritance:

.. autoclass:: syndesi.adapters.events.AdapterReadEvent
   :members:
   :undoc-members:
   :no-show-inheritance:

.. autoclass:: syndesi.adapters.events.AdapterBufferEvent
   :members:
   :undoc-members:
   :no-show-inheritance:

.. autoclass:: syndesi.adapters.events.AdapterTimeoutUpdatedEvent
   :no-members:
   :no-show-inheritance:

.. autoclass:: syndesi.adapters.events.AdapterStopConditionsUpdatedEvent
   :no-members:
   :no-show-inheritance:

Protocol events
---------------

``from syndesi.protocols.protocol import ...``

.. autoclass:: syndesi.protocols.protocol.ProtocolWriteEvent
   :members:
   :undoc-members:
   :no-show-inheritance:

.. autoclass:: syndesi.protocols.protocol.ProtocolFrameEvent
   :members:
   :undoc-members:
   :no-show-inheritance:

.. autoclass:: syndesi.protocols.protocol.ProtocolReadEvent
   :members:
   :undoc-members:
   :no-show-inheritance:

.. autoclass:: syndesi.protocols.protocol.ProtocolBufferEvent
   :members:
   :undoc-members:
   :no-show-inheritance:

.. autoclass:: syndesi.protocols.protocol.ProtocolDecodeErrorEvent
   :members:
   :undoc-members:
   :no-show-inheritance:

Modbus server events
--------------------

``from syndesi.protocols.modbus.server import ...``

.. autoclass:: syndesi.protocols.modbus.server.ModbusConnectionOpenedEvent
   :members:
   :undoc-members:
   :no-show-inheritance:

.. autoclass:: syndesi.protocols.modbus.server.ModbusConnectionClosedEvent
   :members:
   :undoc-members:
   :no-show-inheritance:

.. autoclass:: syndesi.protocols.modbus.server.ModbusRequestHandledEvent
   :members:
   :undoc-members:
   :no-show-inheritance:

.. autoclass:: syndesi.protocols.modbus.server.ModbusHandlerErrorEvent
   :members:
   :undoc-members:
   :no-show-inheritance:
