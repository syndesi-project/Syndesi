# File : bridge.py
# Author : Sébastien Deriaz
# License : GPL
"""
Bridges, drivers that provide a bus (I2C, SPI, serial) to the layers above them

A bridge is a driver for a converter (MCP2221, a custom board, a serial server, ...).
It inherits one interface per bus it provides and implements its methods as ordinary
blocking code, the way any driver is written :

    class MyBoard(Driver, I2CBridge, SerialBridge):
        def i2c_transfer(self, address, data, read_length):
            return bytes.fromhex(self._protocol.query(f"I2C {address} {data.hex()}"))
        ...

    i2c = I2C(MyBoard(Delimited(SerialPort("/dev/ttyUSB0", 115200))), address=0x48)

Every call goes through the bridge's own thread, one at a time. That thread is what
allows the bridge to block : the reactor never runs bridge code, so it stays free to
deliver the answers the bridge waits for. It also serializes the users of the bridge
(several I2C addresses, a SerialPort, ...) without any lock

The thread starts on the first call and stops when the bridge is garbage collected

A bridge has a name, which appears in the descriptors of the adapters it provides
(i2c:MyBoard@0x48) : the name of its class, followed by #2, #3, ... for the other
instances alive at the same time. Every bridge takes a name keyword to choose it, without
its author declaring it :

    left, right = MyBoard(..., name="left"), MyBoard(..., name="right")

The buses of the machine itself are bridges too (LinuxI2C, LinuxSPI) : the kernel is the
converter, and an ioctl blocks for the whole transaction, so it belongs on this thread
"""

from __future__ import annotations

import functools
import inspect
import queue
import threading
import weakref
from abc import ABC, abstractmethod
from collections.abc import Callable
from concurrent.futures import Future
from typing import Any, ClassVar, TypeVar

ResultT = TypeVar("ResultT")

_Task = tuple[Future[Any], Callable[..., Any], tuple[Any, ...]]


class _Worker:
    """The thread of one bridge and its task queue"""

    def __init__(self, name: str) -> None:
        self.tasks: queue.SimpleQueue[_Task | None] = queue.SimpleQueue()
        # The thread only knows the queue : holding the bridge would keep it alive
        self.thread = threading.Thread(
            target=_work, args=(self.tasks,), name=name, daemon=True
        )
        self.thread.start()

    def stop(self) -> None:
        """Let the thread finish the tasks already queued, then exit"""
        self.tasks.put(None)


def _work(tasks: queue.SimpleQueue[_Task | None]) -> None:
    while True:
        task = tasks.get()
        if task is None:
            return
        _execute(task)
        # No reference to the task survives here, while the thread waits for the next
        # one : the task holds a bound method, so it would keep the bridge alive
        del task


def _execute(task: _Task) -> None:
    future, function, args = task
    if not future.set_running_or_notify_cancel():
        return
    try:
        future.set_result(function(*args))
    except BaseException as e:  # pylint: disable=broad-exception-caught
        future.set_exception(e)


# Created on first use rather than in __init__ : a bridge is usually also a Driver,
# whose __init__ doesn't call super(), so Bridge.__init__ could be skipped
_creation_lock = threading.Lock()

# The names in use, so that a default name doesn't repeat one of them
_names: weakref.WeakValueDictionary[str, Bridge] = weakref.WeakValueDictionary()


def _accept_name(init: Callable[..., None]) -> Callable[..., None]:
    """
    Wrap the __init__ of a bridge so that it takes a name keyword

    The signature shown (help, UI) is the original one plus name
    """

    @functools.wraps(init)
    def __init__(self: Bridge, *args: Any, name: str | None = None, **kwargs: Any) -> None:
        if name is not None:
            self.set_bridge_name(name)
        init(self, *args, **kwargs)

    try:
        signature = inspect.signature(init)
    except (TypeError, ValueError):  # pragma: no cover - builtin __init__
        return __init__
    parameters = list(signature.parameters.values())
    position = next(
        (i for i, p in enumerate(parameters) if p.kind is p.VAR_KEYWORD), len(parameters)
    )
    parameters.insert(
        position,
        inspect.Parameter(
            "name", inspect.Parameter.KEYWORD_ONLY, default=None, annotation=str | None
        ),
    )
    __init__.__signature__ = signature.replace(parameters=parameters)  # type: ignore[attr-defined]
    return __init__


class Bridge:
    """
    Base of every bridge : runs its methods one at a time on its own thread

    Not used directly, inherit I2CBridge, SPIBridge or SerialBridge
    """

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        init = cls.__dict__.get("__init__")
        # A class whose __init__ already takes a name keeps it for itself
        if init is not None and "name" not in inspect.signature(init).parameters:
            # setattr : an assignment makes pylint believe Bridge has an __init__ that
            # every bridge must call (super-init-not-called)
            setattr(cls, "__init__", _accept_name(init))  # noqa: B010

    @property
    def bridge_name(self) -> str:
        """
        Name of the bridge, in the descriptors of its adapters

        The class name by default, followed by #2, #3, ... if it is already used
        """
        name: str | None = self.__dict__.get("_bridge_name")
        if name is not None:
            return name
        with _creation_lock:
            name = self.__dict__.get("_bridge_name")
            if name is None:
                base = type(self).__name__
                name, number = base, 1
                while name in _names:
                    number += 1
                    name = f"{base}#{number}"
                self._register_name(name)
            return name

    def set_bridge_name(self, name: str) -> None:
        """
        Choose the name of the bridge, before the adapters that use it are created

        The name keyword of the constructor calls it
        """
        if not name:
            raise ValueError("A bridge name can't be empty")
        with _creation_lock:
            self._register_name(name)

    def _register_name(self, name: str) -> None:
        """Under _creation_lock"""
        self.__dict__["_bridge_name"] = name
        _names[name] = self

    def run(
        self, function: Callable[..., ResultT], *args: Any
    ) -> Future[ResultT]:
        """
        Run function(*args) on the bridge thread and return its future

        Called from the bridge thread itself (a bridge method using another one), the
        function runs right away instead : waiting for its own queue would never end
        """
        worker = self._worker()
        if threading.current_thread() is worker.thread:
            future: Future[ResultT] = Future()
            _execute((future, function, args))
            return future
        future = Future()
        worker.tasks.put((future, function, args))
        return future

    def close_bridge(self) -> None:
        """
        Stop the bridge thread once the queued calls are done

        Optional : the thread also stops when the bridge is garbage collected. The next
        call starts a new one
        """
        with _creation_lock:
            worker: _Worker | None = self.__dict__.pop("_bridge_worker", None)
        if worker is not None:
            worker.stop()

    def _worker(self) -> _Worker:
        worker: _Worker | None = self.__dict__.get("_bridge_worker")
        if worker is not None:
            return worker
        with _creation_lock:
            worker = self.__dict__.get("_bridge_worker")
            if worker is None:
                worker = _Worker(f"syndesi-bridge-{type(self).__name__}")
                self.__dict__["_bridge_worker"] = worker
                weakref.finalize(self, worker.stop)
            return worker

    def __str__(self) -> str:
        return self.bridge_name


class I2CBridge(Bridge, ABC):
    """Interface of a bridge that provides an I2C bus, see I2C"""

    @abstractmethod
    def i2c_transfer(self, address: int, data: bytes, read_length: int) -> bytes:
        """
        Write data to the device at address, then read read_length bytes from it

        Runs on the bridge thread, it can block. The read follows the write with a
        repeated start. Either part can be empty : read_length=0 is a plain write,
        data=b"" a plain read

        Parameters
        ----------
        address : int
            7-bit address of the device
        data : bytes
        read_length : int

        Returns
        -------
        bytes
            Exactly read_length bytes
        """


class SPIBridge(Bridge, ABC):
    """
    Interface of a bridge that provides an SPI bus, see SPI

    The SPI mode and clock are settings of the bridge, configured by its driver
    """

    @abstractmethod
    def spi_transfer(self, cs: int, data: bytes) -> bytes:
        """
        Select the device on chip select cs, exchange data, deselect it

        Runs on the bridge thread, it can block

        Parameters
        ----------
        cs : int
            Chip select line
        data : bytes

        Returns
        -------
        bytes
            The bytes received while data was sent, as many as data
        """


class SerialBridge(Bridge, ABC):
    """
    Interface of a bridge that provides a serial port, see SerialPort

    Syndesi calls serial_read() in a loop while the SerialPort is open, in between the
    other calls to the bridge. A call that returns nothing is followed by a pause, so
    that the loop runs at most once every SERIAL_POLL_PERIOD seconds
    """

    SERIAL_POLL_PERIOD: ClassVar[float] = 0.05

    @abstractmethod
    def serial_configure(
        self, baudrate: int, bytesize: int, parity: str, stopbits: int
    ) -> None:
        """
        Apply the line settings, called each time the SerialPort opens

        Runs on the bridge thread, it can block. parity is one of the Parity values
        """

    @abstractmethod
    def serial_write(self, data: bytes) -> None:
        """Send data on the serial line. Runs on the bridge thread, it can block"""

    @abstractmethod
    def serial_read(self, timeout: float) -> bytes:
        """
        Return the bytes received on the serial line since the last call

        Runs on the bridge thread, it can block, but for timeout seconds at most : the
        other users of the bridge wait meanwhile. Returns b"" if nothing came
        """
