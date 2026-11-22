Accept TCP connections
======================

``IPServer`` listens on a port. Reading from it waits for a client and returns it as a
ready-to-use ``IP`` adapter.

Accept one client
-----------------

.. code-block:: python

   from syndesi import IPServer

   server = IPServer("0.0.0.0", 8888)
   client = server.read()            # blocks until someone connects
   print(client.descriptor.address)  # '192.168.1.57'
   client.write(b"Welcome\n")
   print(client.read())

``0.0.0.0`` listens on every network interface, ``127.0.0.1`` on this computer only.

Listen before the clients arrive
--------------------------------

The server starts listening at its first ``read()``. If clients may connect before
that, open it first:

.. code-block:: python

   server = IPServer("127.0.0.1", 8888)
   server.open()   # listening from now on

Frame the clients' messages
---------------------------

Stop conditions given to the server apply to every client:

.. code-block:: python

   from syndesi import IPServer, Termination

   server = IPServer("0.0.0.0", 8888, stop_conditions=[Termination(b"\n")])

Serve several clients
---------------------

One thread per client:

.. code-block:: python

   import threading

   from syndesi import Delimited, IPServer
   from syndesi.errors import AdapterError

   def serve(client):
       line = Delimited(client, timeout=None)   # clients may stay silent for a long time
       try:
           while True:
               command = line.read()
               line.write(command.upper())
       except AdapterError:
           pass   # client left

   server = IPServer("0.0.0.0", 8888)
   while True:
       threading.Thread(target=serve, args=(server.read(),), daemon=True).start()

.. note::

   The protocol gives its timeout to the client adapter: ``timeout=None`` on
   ``Delimited`` is enough to wait without limit. See :ref:`timeouts`.

Stop the server
---------------

.. code-block:: python

   server.close()

Async
-----

.. code-block:: python

   from syndesi import AsyncIPServer

   server = AsyncIPServer("0.0.0.0", 8888)
   client = await server.read()      # an AsyncIP
   await client.write(b"Welcome\n")
