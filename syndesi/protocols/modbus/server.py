# File : server.py
# Author : Sébastien Deriaz
# License : GPL
"""
Modbus servers (slaves), sync and async
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import struct
import threading
from collections import defaultdict
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any, TypeVar, cast

from syndesi.adapters.serialport import AsyncSerialPort, SerialPort

from ...adapters.adapter import Adapter, AsyncAdapter
from ...adapters.events import SyndesiEvent
from ...adapters.ipserver import AsyncIPServer, IPServer
from ...tools.errors import AdapterError, ProtocolReadError
from ...tools.log_settings import LoggerAlias
from ..protocol import (
    AsyncProtocol,
    Protocol,
    ProtocolEvent,
)
from .backend import (
    ModbusBackend,
    ModbusSerialType,
    ModbusTCPBackend,
    _serial_backend,
)
from .common import (
    ENDIAN,
    MODBUS_TCP_DEFAULT_PORT,
    DiagnosticsCode,
    ExceptionCode,
    ModbusException,
)
from .sdu import (
    DiagnosticsRequestSDU,
    DiagnosticsResponseSDU,
    ExceptionResponseSDU,
    GetCommEventCounterRequestSDU,
    GetCommEventCounterResponseSDU,
    GetCommEventLogRequestSDU,
    GetCommEventLogResponseSDU,
    MaskWriteRegisterRequestSDU,
    MaskWriteRegisterResponseSDU,
    ModbusRequestSDU,
    ModbusResponseSDU,
    ModbusSDU,
    ReadCoilsRequestSDU,
    ReadCoilsResponseSDU,
    ReadDiscreteInputsRequestSDU,
    ReadDiscreteInputsResponseSDU,
    ReadExceptionStatusRequestSDU,
    ReadExceptionStatusResponseSDU,
    ReadFifoQueueRequestSDU,
    ReadFifoQueueResponseSDU,
    ReadFileRecordRequestSDU,
    ReadFileRecordResponseSDU,
    ReadHoldingRegistersRequestSDU,
    ReadHoldingRegistersResponseSDU,
    ReadInputRegistersRequestSDU,
    ReadInputRegistersResponseSDU,
    ReadWriteMultipleRegistersRequestSDU,
    ReadWriteMultipleRegistersResponseSDU,
    ReportServerIdRequestSDU,
    ReportServerIdResponseSDU,
    WriteFileRecordRequestSDU,
    WriteFileRecordResponseSDU,
    WriteMultipleCoilsRequestSDU,
    WriteMultipleCoilsResponseSDU,
    WriteMultipleRegistersRequestSDU,
    WriteMultipleRegistersResponseSDU,
    WriteSingleCoilRequestSDU,
    WriteSingleCoilResponseSDU,
    WriteSingleRegisterRequestSDU,
    WriteSingleRegisterResponseSDU,
)

# ┌────────┐
# │ Server │
# └────────┘

FIFO_MAX_COUNT = 31
MAX_RECORD_NUMBER = 9999
COMM_EVENT_STATUS_READY = 0x0000
RESTART_CLEAR_EVENT_LOG = b"\xff\x00"

# Diagnostics answered with the value of a counter
_DIAGNOSTICS_COUNTERS = {
    DiagnosticsCode.RETURN_BUS_MESSAGE_COUNT,
    DiagnosticsCode.RETURN_BUS_COMMUNICATION_ERROR_COUNT,
    DiagnosticsCode.RETURN_BUS_EXCEPTION_ERROR_COUNT,
    DiagnosticsCode.RETURN_SERVER_MESSAGE_COUNT,
    DiagnosticsCode.RETURN_SERVER_NO_RESPONSE_COUNT,
    DiagnosticsCode.RETURN_SERVER_NAK_COUNT,
    DiagnosticsCode.RETURN_SERVER_BUSY_COUNT,
    DiagnosticsCode.RETURN_BUS_CHARACTER_OVERRUN_COUNT,
}

RequestHandlerT = TypeVar("RequestHandlerT", bound=ModbusRequestSDU)


@dataclass
class ModbusConnectionOpenedEvent(ProtocolEvent):
    """A server started answering on a connection : a TCP client, or the serial line"""

    adapter: Adapter[Any, bytes] | AsyncAdapter[Any, bytes]


@dataclass
class ModbusConnectionClosedEvent(ProtocolEvent):
    """A server stopped answering on a connection"""

    adapter: Adapter[Any, bytes] | AsyncAdapter[Any, bytes]


@dataclass
class ModbusRequestHandledEvent(ProtocolEvent):
    """
    A server handled a request

    request is an ExceptionResponseSDU for a request the backend couldn't accept.
    response is None when nothing was answered
    """

    request: ModbusSDU
    response: ModbusResponseSDU[Any] | None


@dataclass
class ModbusHandlerErrorEvent(ProtocolEvent):
    """A handler raised something else than a ModbusException, a bug in the handler"""

    request: ModbusRequestSDU
    error: Exception


class ModbusServerCommon:
    """
    Data model and request handling shared by ModbusServer and AsyncModbusServer

    Every function code has a default handler, default_handler(), working on the data
    model below. set_handler() replaces it for one function code. Addresses are the data
    model ones, starting at 1, like the client methods

    Attributes
    ----------
    coils : dict[int, bool]
    discrete_inputs : dict[int, bool]
    holding_registers : dict[int, int]
    input_registers : dict[int, int]
    files : dict[int, dict[int, int]]
        Registers of the files, by file number then record number
    fifos : dict[int, list[int]]
        FIFO queues by address, 31 values at most
    exception_status : int
        Answer to read_exception_status
    server_id : bytes
    run_indicator_status : bool
    additional_data : bytes
        Answer to report_server_id
    diagnostic_register : int
    counters : dict[DiagnosticsCode, int]
        Diagnostics counters. The bus, server message, exception and no response
        counters are kept up to date, the others are left to the user
    event_count : int
        Communication event counter
    listen_only : bool
        Set by the force listen only mode diagnostic, nothing is answered until the
        restart communications option diagnostic
    """

    def __init__(self) -> None:
        self.coils: defaultdict[int, bool] = defaultdict(bool)
        self.discrete_inputs: defaultdict[int, bool] = defaultdict(bool)
        self.holding_registers: defaultdict[int, int] = defaultdict(int)
        self.input_registers: defaultdict[int, int] = defaultdict(int)
        self.files: defaultdict[int, defaultdict[int, int]] = defaultdict(
            lambda: defaultdict(int)
        )
        self.fifos: defaultdict[int, list[int]] = defaultdict(list)
        self.exception_status = 0
        self.server_id = b"syndesi"
        self.run_indicator_status = True
        self.additional_data = b""
        self.diagnostic_register = 0
        self.counters: defaultdict[DiagnosticsCode, int] = defaultdict(int)
        self.event_count = 0
        self.listen_only = False

        self._handlers: dict[type[ModbusRequestSDU], Callable[[Any], Any]] = {}
        self._callbacks: list[Callable[[SyndesiEvent], None]] = []
        self._logger = logging.getLogger(LoggerAlias.PROTOCOL.value)

    def register_event_callback(self, callback: Callable[[SyndesiEvent], None]) -> None:
        """
        Register an event callback

        It receives the server events, and the protocol and adapter events of every
        connection. It runs on the reactor thread or on the thread (task) serving the
        connection, and must not block
        """
        self._callbacks.append(callback)

    def clear_event_callbacks(self) -> None:
        """Remove every event callback"""
        self._callbacks.clear()

    def _emit(self, event: SyndesiEvent) -> None:
        for callback in list(self._callbacks):
            try:
                callback(event)
            except Exception as e:  # pylint: disable=broad-exception-caught
                self._logger.exception(f"Event callback failed : {e}")

    # ┌──────────────────┐
    # │ Request handling │
    # └──────────────────┘

    def default_handler(
        self, request: ModbusRequestSDU
    ) -> ModbusResponseSDU[Any] | None:
        """
        Answer a request from the data model, None when it has no answer

        Raises ModbusException for the requests that are answered with an exception.
        A custom handler can call it to keep the default behaviour
        """
        # pylint: disable=too-many-return-statements
        match request:
            case ReadCoilsRequestSDU(address, n):
                return ReadCoilsResponseSDU(_read(self.coils, address, n))
            case ReadDiscreteInputsRequestSDU(address, n):
                return ReadDiscreteInputsResponseSDU(
                    _read(self.discrete_inputs, address, n)
                )
            case ReadHoldingRegistersRequestSDU(address, n):
                return ReadHoldingRegistersResponseSDU(
                    _read(self.holding_registers, address, n)
                )
            case ReadInputRegistersRequestSDU(address, n):
                return ReadInputRegistersResponseSDU(
                    _read(self.input_registers, address, n)
                )
            case WriteSingleCoilRequestSDU(address, status):
                self.coils[address] = status
                return WriteSingleCoilResponseSDU(address, status)
            case WriteSingleRegisterRequestSDU(address, value):
                self.holding_registers[address] = value
                return WriteSingleRegisterResponseSDU(address, value)
            case ReadExceptionStatusRequestSDU():
                return ReadExceptionStatusResponseSDU(self.exception_status)
            case DiagnosticsRequestSDU(code, data):
                return self._diagnostics(code, data)
            case GetCommEventCounterRequestSDU():
                return GetCommEventCounterResponseSDU(
                    COMM_EVENT_STATUS_READY, self.event_count
                )
            case GetCommEventLogRequestSDU():
                # The events themselves aren't logged
                return GetCommEventLogResponseSDU(
                    COMM_EVENT_STATUS_READY,
                    self.event_count,
                    self.counters[DiagnosticsCode.RETURN_BUS_MESSAGE_COUNT],
                    b"",
                )
            case WriteMultipleCoilsRequestSDU(address, values):
                _write(self.coils, address, values)
                return WriteMultipleCoilsResponseSDU(address, len(values))
            case WriteMultipleRegistersRequestSDU(address, values):
                _write(self.holding_registers, address, values)
                return WriteMultipleRegistersResponseSDU(address, len(values))
            case ReportServerIdRequestSDU():
                return ReportServerIdResponseSDU(
                    self.server_id, self.run_indicator_status, self.additional_data
                )
            case ReadFileRecordRequestSDU(records):
                return ReadFileRecordResponseSDU(
                    [self._read_file(*record) for record in records]
                )
            case WriteFileRecordRequestSDU(records):
                for record in records:
                    self._write_file(*record)
                return WriteFileRecordResponseSDU(records)
            case MaskWriteRegisterRequestSDU(address, and_mask, or_mask):
                value = self.holding_registers[address]
                self.holding_registers[address] = (value & and_mask) | (
                    or_mask & ~and_mask
                )
                return MaskWriteRegisterResponseSDU(address, and_mask, or_mask)
            case ReadWriteMultipleRegistersRequestSDU(
                read_address, n, write_address, values
            ):
                # The write is done before the read
                _write(self.holding_registers, write_address, values)
                return ReadWriteMultipleRegistersResponseSDU(
                    _read(self.holding_registers, read_address, n)
                )
            case ReadFifoQueueRequestSDU(address):
                values = self.fifos[address]
                if len(values) > FIFO_MAX_COUNT:
                    raise ModbusException(ExceptionCode.ILLEGAL_DATA_VALUE)
                return ReadFifoQueueResponseSDU(list(values))
        # Encapsulated interface transport has no default behaviour
        raise ModbusException(ExceptionCode.ILLEGAL_FUNCTION)

    def _diagnostics(
        self, code: DiagnosticsCode, data: bytes
    ) -> DiagnosticsResponseSDU | None:
        match code:
            case DiagnosticsCode.RETURN_QUERY_DATA:
                pass
            case DiagnosticsCode.RESTART_COMMUNICATIONS_OPTION:
                self.listen_only = False
                if data == RESTART_CLEAR_EVENT_LOG:
                    self.event_count = 0
            case DiagnosticsCode.RETURN_DIAGNOSTIC_REGISTER:
                data = struct.pack(ENDIAN + "H", self.diagnostic_register)
            case DiagnosticsCode.FORCE_LISTEN_ONLY_MODE:
                self.listen_only = True
                return None
            case DiagnosticsCode.CLEAR_COUNTERS_AND_DIAGNOSTIC_REGISTER:
                self.counters.clear()
                self.diagnostic_register = 0
            case DiagnosticsCode.CLEAR_OVERRUN_COUNTER_AND_FLAG:
                self.counters[DiagnosticsCode.RETURN_BUS_CHARACTER_OVERRUN_COUNT] = 0
            case _ if code in _DIAGNOSTICS_COUNTERS:
                data = struct.pack(ENDIAN + "H", self.counters[code] & 0xFFFF)
            case _:
                # The ASCII input delimiter cannot be changed
                raise ModbusException(ExceptionCode.ILLEGAL_FUNCTION)
        return DiagnosticsResponseSDU(code, data)

    def _read_file(self, file_number: int, record_number: int, length: int) -> bytes:
        _check_file_record(file_number, record_number, length)
        registers = self.files[file_number]
        return struct.pack(
            ENDIAN + f"{length}H",
            *(registers[record_number + i] for i in range(length)),
        )

    def _write_file(self, file_number: int, record_number: int, data: bytes) -> None:
        values = struct.unpack(ENDIAN + f"{len(data) // 2}H", data)
        _check_file_record(file_number, record_number, len(values))
        _write(self.files[file_number], record_number, values)

    # ┌──────────────┐
    # │ Bookkeeping  │
    # └──────────────┘

    def _handler(self, request: ModbusRequestSDU) -> Callable[[Any], Any]:
        return self._handlers.get(type(request), self.default_handler)

    def _accept(self, payload: ModbusSDU) -> bool:
        """Count a received request, False if it must be ignored (listen only mode)"""
        self.counters[DiagnosticsCode.RETURN_BUS_MESSAGE_COUNT] += 1
        self.counters[DiagnosticsCode.RETURN_SERVER_MESSAGE_COUNT] += 1
        restart = (
            isinstance(payload, DiagnosticsRequestSDU)
            and payload.code == DiagnosticsCode.RESTART_COMMUNICATIONS_OPTION
        )
        if self.listen_only and not restart:
            self.counters[DiagnosticsCode.RETURN_SERVER_NO_RESPONSE_COUNT] += 1
            return False
        return True

    def _exception_response(
        self, request: ModbusRequestSDU, error: Exception
    ) -> ExceptionResponseSDU:
        """The answer to a request whose handler raised"""
        if isinstance(error, ModbusException):
            return ExceptionResponseSDU(request.function_code, error.exception_code)
        self._logger.exception(f"Modbus handler failed on {request}")
        self._emit(ModbusHandlerErrorEvent(request, error))
        return ExceptionResponseSDU(
            request.function_code, ExceptionCode.SERVER_DEVICE_FAILURE
        )

    def _account(
        self, request: ModbusSDU, response: ModbusResponseSDU[Any] | None
    ) -> ModbusResponseSDU[Any] | None:
        """Count an answer and return it"""
        if response is None:
            self.counters[DiagnosticsCode.RETURN_SERVER_NO_RESPONSE_COUNT] += 1
        elif isinstance(response, ExceptionResponseSDU):
            self.counters[DiagnosticsCode.RETURN_BUS_EXCEPTION_ERROR_COUNT] += 1
        elif not isinstance(
            request, (GetCommEventCounterRequestSDU, GetCommEventLogRequestSDU)
        ):
            self.event_count += 1
        return response

    def _count_communication_error(self) -> None:
        self.counters[DiagnosticsCode.RETURN_BUS_COMMUNICATION_ERROR_COUNT] += 1


def _read(table: defaultdict[int, Any], address: int, n: int) -> list[Any]:
    return [table[address + i] for i in range(n)]


def _write(table: defaultdict[int, Any], address: int, values: Sequence[Any]) -> None:
    for i, value in enumerate(values):
        table[address + i] = value


def _check_file_record(file_number: int, record_number: int, length: int) -> None:
    if file_number == 0 or record_number + length - 1 > MAX_RECORD_NUMBER:
        raise ModbusException(ExceptionCode.ILLEGAL_DATA_ADDRESS)


class ModbusServer(ModbusServerCommon):
    """
    Modbus server (slave) : Modbus TCP with an IPServer, RTU or ASCII with a SerialPort

    In TCP, every client is served by its own thread. Handlers can run concurrently,
    each call holds a lock so the data model stays consistent

    Parameters
    ----------
    adapter : IPServer or SerialPort
    serial_type : {'RTU', 'ASCII'}
        Serial flavour, ignored with an IPServer. 'RTU' by default
    slave_address : int or None
        1 to 247, required for RTU and ASCII, unused by TCP

    Examples
    --------
    >>> server = ModbusServer(IPServer('0.0.0.0'))
    >>> server.holding_registers[1] = 1234
    >>> server.set_handler(ReadCoilsRequestSDU, lambda request: ...)
    >>> server.serve_forever()
    """

    def __init__(
        self,
        adapter: IPServer | SerialPort,
        *,
        serial_type: str = ModbusSerialType.RTU.value,
        slave_address: int | None = None,
    ) -> None:
        super().__init__()
        self._lock = threading.Lock()
        self._protocols: set[Protocol[ModbusBackend, bytes, ModbusSDU]] = set()
        self._stopped = False

        # One of the two is set : the server that accepts the TCP clients, or the
        # serial line with its backend
        self._ip_server: IPServer | None = None
        self._serial: tuple[Adapter[Any, bytes], ModbusBackend] | None = None
        if isinstance(adapter, IPServer):
            adapter.set_default_port(MODBUS_TCP_DEFAULT_PORT)
            self._ip_server = adapter
        elif isinstance(adapter, SerialPort):
            backend = _serial_backend(
                serial_type, slave_address, adapter.descriptor.baudrate, server=True
            )
            self._serial = (adapter, backend)
        else:
            raise ValueError(f"Invalid adapter : {adapter}")

    def set_handler(
        self,
        request_type: type[RequestHandlerT],
        handler: Callable[[RequestHandlerT], ModbusResponseSDU[Any] | None] | None,
    ) -> None:
        """
        Answer the requests of a type with a custom handler, None for the default one

        The handler returns the response, None for no response, or raises
        ModbusException to answer with an exception
        """
        if handler is None:
            self._handlers.pop(request_type, None)
        else:
            self._handlers[request_type] = handler

    def serve_forever(self) -> None:
        """Answer the requests until stop() is called"""
        if self._serial is not None:
            self._serve(*self._serial)
            return

        assert self._ip_server is not None
        threads: list[threading.Thread] = []
        while True:
            try:
                client = self._ip_server.read()
            except AdapterError:
                break  # stop() closed the server
            thread = threading.Thread(
                target=self._serve,
                args=(client, ModbusTCPBackend(server=True)),
                daemon=True,
            )
            thread.start()
            threads = [t for t in threads if t.is_alive()] + [thread]

        for thread in threads:
            thread.join()

    def stop(self) -> None:
        """Stop serving : close the server and every connection"""
        if self._ip_server is not None:
            self._ip_server.close()
        with self._lock:
            self._stopped = True
            protocols = list(self._protocols)
        for protocol in protocols:
            protocol.close()

    def _serve(self, adapter: Adapter[Any, bytes], backend: ModbusBackend) -> None:
        """Answer the requests of one connection until it closes"""
        protocol: Protocol[ModbusBackend, bytes, ModbusSDU] = Protocol(
            adapter, backend, event_callback=self._emit
        )
        with self._lock:
            self._protocols.add(protocol)
            stopped = self._stopped
        if stopped:
            protocol.close()  # stop() came before this connection was known
        self._emit(ModbusConnectionOpenedEvent(adapter))
        try:
            while True:
                try:
                    payload = protocol.read()
                except ProtocolReadError:
                    with self._lock:
                        self._count_communication_error()
                    continue
                response = self._answer(payload)
                self._emit(ModbusRequestHandledEvent(payload, response))
                if response is not None:
                    protocol.write(response)
        except AdapterError:
            pass  # the client left, or stop() closed the connection
        finally:
            with self._lock:
                self._protocols.discard(protocol)
            protocol.close()
            self._emit(ModbusConnectionClosedEvent(adapter))

    def _answer(self, payload: ModbusSDU) -> ModbusResponseSDU[Any] | None:
        with self._lock:
            if not self._accept(payload):
                return None
            if not isinstance(payload, ModbusRequestSDU):
                # An invalid request, the backend made the exception response
                return self._account(payload, cast(ModbusResponseSDU[Any], payload))
            try:
                response = self._handler(payload)(payload)
            except Exception as e:  # pylint: disable=broad-exception-caught
                response = self._exception_response(payload, e)
            return self._account(payload, response)


class AsyncModbusServer(ModbusServerCommon):
    """
    Async Modbus server, same parameters as ModbusServer with async adapters

    In TCP, every client is served by its own task. Handlers can be functions or
    coroutine functions

    Examples
    --------
    >>> server = AsyncModbusServer(AsyncIPServer('0.0.0.0'))
    >>> server.holding_registers[1] = 1234
    >>> await server.serve_forever()
    """

    def __init__(
        self,
        adapter: AsyncIPServer | AsyncSerialPort,
        *,
        serial_type: str = ModbusSerialType.RTU.value,
        slave_address: int | None = None,
    ) -> None:
        super().__init__()
        self._protocols: set[AsyncProtocol[ModbusBackend, bytes, ModbusSDU]] = set()
        self._stopped = False

        # One of the two is set : the server that accepts the TCP clients, or the
        # serial line with its backend
        self._ip_server: AsyncIPServer | None = None
        self._serial: tuple[AsyncAdapter[Any, bytes], ModbusBackend] | None = None
        if isinstance(adapter, AsyncIPServer):
            adapter.set_default_port(MODBUS_TCP_DEFAULT_PORT)
            self._ip_server = adapter
        elif isinstance(adapter, AsyncSerialPort):
            backend = _serial_backend(
                serial_type, slave_address, adapter.descriptor.baudrate, server=True
            )
            self._serial = (adapter, backend)
        else:
            raise ValueError(f"Invalid adapter : {adapter}")

    def set_handler(
        self,
        request_type: type[RequestHandlerT],
        handler: (
            Callable[[RequestHandlerT], ModbusResponseSDU[Any] | None]
            | Callable[[RequestHandlerT], Awaitable[ModbusResponseSDU[Any] | None]]
            | None
        ),
    ) -> None:
        """
        Answer the requests of a type with a custom handler, None for the default one

        The handler, a function or a coroutine function, returns the response, None for
        no response, or raises ModbusException to answer with an exception
        """
        if handler is None:
            self._handlers.pop(request_type, None)
        else:
            self._handlers[request_type] = handler

    async def serve_forever(self) -> None:
        """Answer the requests until stop() is called"""
        if self._serial is not None:
            await self._serve(*self._serial)
            return

        if self._ip_server is None:
            raise RuntimeError("Missing ip server")
        async with asyncio.TaskGroup() as tasks:
            while True:
                try:
                    client = await self._ip_server.read()
                except AdapterError:
                    break  # stop() closed the server
                tasks.create_task(self._serve(client, ModbusTCPBackend(server=True)))

    async def stop(self) -> None:
        """Stop serving : close the server and every connection"""
        self._stopped = True
        if self._ip_server is not None:
            await self._ip_server.close()
        for protocol in list(self._protocols):
            await protocol.close()

    async def _serve(
        self, adapter: AsyncAdapter[Any, bytes], backend: ModbusBackend
    ) -> None:
        """Answer the requests of one connection until it closes"""
        protocol: AsyncProtocol[ModbusBackend, bytes, ModbusSDU] = AsyncProtocol(
            adapter, backend, event_callback=self._emit
        )
        self._protocols.add(protocol)
        if self._stopped:
            await protocol.close()  # stop() came before this connection was known
        self._emit(ModbusConnectionOpenedEvent(adapter))
        try:
            while True:
                try:
                    payload = await protocol.read()
                except ProtocolReadError:
                    self._count_communication_error()
                    continue
                response = await self._answer(payload)
                self._emit(ModbusRequestHandledEvent(payload, response))
                if response is not None:
                    await protocol.write(response)
        except AdapterError:
            pass  # the client left, or stop() closed the connection
        finally:
            self._protocols.discard(protocol)
            await protocol.close()
            self._emit(ModbusConnectionClosedEvent(adapter))

    async def _answer(self, payload: ModbusSDU) -> ModbusResponseSDU[Any] | None:
        if not self._accept(payload):
            return None
        if not isinstance(payload, ModbusRequestSDU):
            # An invalid request, the backend made the exception response
            return self._account(payload, cast(ModbusResponseSDU[Any], payload))
        try:
            response = self._handler(payload)(payload)
            if inspect.isawaitable(response):
                response = await response
        except Exception as e:  # pylint: disable=broad-exception-caught
            response = self._exception_response(payload, e)
        return self._account(payload, response)
