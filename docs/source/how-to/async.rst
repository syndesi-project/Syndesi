Use async / await
=================

Every adapter and protocol has an async twin, prefixed with ``Async``. The methods and
parameters are the same, they just need ``await``.

=====================  ==========================
Sync                   Async
=====================  ==========================
``IP``                 ``AsyncIP``
``SerialPort``         ``AsyncSerialPort``
``Visa``               ``AsyncVisa``
``IPServer``           ``AsyncIPServer``
``Delimited``          ``AsyncDelimited``
``Raw``                ``AsyncRaw``
``SCPI``               ``AsyncSCPI``
``Modbus``             ``AsyncModbus``
``ModbusServer``       ``AsyncModbusServer``
``auto_adapter``       ``auto_async_adapter``
=====================  ==========================

Side by side
------------

.. tab-set::

   .. tab-item:: Sync
      :sync: sync

      .. code-block:: python

         from syndesi import IP, SCPI

         dmm = SCPI(IP("192.168.1.20"))
         print(dmm.query("*IDN?"))

   .. tab-item:: Async
      :sync: async

      .. code-block:: python

         import asyncio

         from syndesi import AsyncIP, AsyncSCPI

         async def main():
             dmm = AsyncSCPI(AsyncIP("192.168.1.20"))
             print(await dmm.query("*IDN?"))

         asyncio.run(main())

Talk to several devices at once
-------------------------------

The point of async: wait for several devices at the same time.

.. code-block:: python

   import asyncio

   from syndesi import AsyncIP, AsyncSCPI

   async def identify(address: str) -> str:
       return await AsyncSCPI(AsyncIP(address)).query("*IDN?")

   async def main():
       names = await asyncio.gather(
           identify("192.168.1.20"),
           identify("192.168.1.21"),
           identify("192.168.1.22"),
       )
       print(names)

   asyncio.run(main())

Open and close with ``async with``
----------------------------------

.. code-block:: python

   async with AsyncIP("192.168.1.10", 5025) as dev:
       await dev.write(b"*RST\n")

Cancel a read
-------------

Async reads can be cancelled like any coroutine. A frame arriving afterwards stays in
the buffer for the next read:

.. code-block:: python

   try:
       frame = await asyncio.wait_for(dev.read(timeout=None), 0.5)
   except TimeoutError:
       print("nothing within 0.5 s")

.. seealso::

   :doc:`/explanation/engine` explains why sync and async behave identically: they
   share the same engine.
