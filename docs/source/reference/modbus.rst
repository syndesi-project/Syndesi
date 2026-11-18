Modbus
======

Modbus TCP, RTU and ASCII, client and server. Guides: :doc:`/how-to/modbus-client`,
:doc:`/how-to/modbus-server`.

Client
------

.. autoclass:: syndesi.protocols.modbus.Modbus
   :members:
   :exclude-members: query, query_detailed, read, read_detailed, write, write_raw,
                     open, close, set_timeout, clear_buffer, clear_event_callbacks
   :no-show-inheritance:

.. autoclass:: syndesi.protocols.modbus.AsyncModbus
   :no-members:
   :no-show-inheritance:

Multi-register values
---------------------

.. autoclass:: syndesi.protocols.modbus.ModbusMultiRegisterValue
   :members:
   :no-show-inheritance:

.. autoclass:: syndesi.protocols.modbus.Endian
   :members:
   :undoc-members:
   :no-show-inheritance:

Server
------

.. autoclass:: syndesi.protocols.modbus.ModbusServer
   :members: set_handler, serve_forever, stop, default_handler,
             register_event_callback, clear_event_callbacks
   :no-show-inheritance:

.. autoclass:: syndesi.protocols.modbus.AsyncModbusServer
   :members: set_handler, serve_forever, stop
   :no-show-inheritance:

Data model
~~~~~~~~~~

Attributes shared by both servers:

.. autoclass:: syndesi.protocols.modbus.server.ModbusServerCommon
   :no-members:
   :no-show-inheritance:

Errors
------

.. autoexception:: syndesi.protocols.modbus.ModbusException
   :no-members:
   :no-show-inheritance:

.. autoclass:: syndesi.protocols.modbus.ExceptionCode
   :members:
   :undoc-members:
   :no-show-inheritance:

Requests and responses
----------------------

Custom server handlers receive a request object and return a response object, both
from ``syndesi.protocols.modbus``. Each function code has a pair:

.. list-table::
   :header-rows: 1

   * - Function
     - Request
     - Response
   * - Read coils
     - ``ReadCoilsRequestSDU``
     - ``ReadCoilsResponseSDU``
   * - Read discrete inputs
     - ``ReadDiscreteInputsRequestSDU``
     - ``ReadDiscreteInputsResponseSDU``
   * - Read holding registers
     - ``ReadHoldingRegistersRequestSDU``
     - ``ReadHoldingRegistersResponseSDU``
   * - Read input registers
     - ``ReadInputRegistersRequestSDU``
     - ``ReadInputRegistersResponseSDU``
   * - Write single coil
     - ``WriteSingleCoilRequestSDU``
     - ``WriteSingleCoilResponseSDU``
   * - Write single register
     - ``WriteSingleRegisterRequestSDU``
     - ``WriteSingleRegisterResponseSDU``
   * - Write multiple coils
     - ``WriteMultipleCoilsRequestSDU``
     - ``WriteMultipleCoilsResponseSDU``
   * - Write multiple registers
     - ``WriteMultipleRegistersRequestSDU``
     - ``WriteMultipleRegistersResponseSDU``
   * - Mask write register
     - ``MaskWriteRegisterRequestSDU``
     - ``MaskWriteRegisterResponseSDU``
   * - Read/write registers
     - ``ReadWriteMultipleRegistersRequestSDU``
     - ``ReadWriteMultipleRegistersResponseSDU``
   * - Read FIFO queue
     - ``ReadFifoQueueRequestSDU``
     - ``ReadFifoQueueResponseSDU``
   * - Read file record
     - ``ReadFileRecordRequestSDU``
     - ``ReadFileRecordResponseSDU``
   * - Write file record
     - ``WriteFileRecordRequestSDU``
     - ``WriteFileRecordResponseSDU``
   * - Read exception status
     - ``ReadExceptionStatusRequestSDU``
     - ``ReadExceptionStatusResponseSDU``
   * - Diagnostics
     - ``DiagnosticsRequestSDU``
     - ``DiagnosticsResponseSDU``
   * - Get comm event counter
     - ``GetCommEventCounterRequestSDU``
     - ``GetCommEventCounterResponseSDU``
   * - Get comm event log
     - ``GetCommEventLogRequestSDU``
     - ``GetCommEventLogResponseSDU``
   * - Report server ID
     - ``ReportServerIdRequestSDU``
     - ``ReportServerIdResponseSDU``
   * - Encapsulated interface
     - ``EncapsulatedInterfaceTransportRequestSDU``
     - ``EncapsulatedInterfaceTransportResponseSDU``
