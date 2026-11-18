Your first connection
=====================

In this tutorial you will install Syndesi, start a tiny server on your computer, and
exchange your first messages with it. You will meet the three methods you will use
every day: ``write``, ``read`` and ``query``.

.. rubric:: What you need

Python 3.11 or newer, and two terminal windows.

Install Syndesi
---------------

.. code-block:: console

   $ pip install syndesi

Check that it worked:

.. code-block:: console

   $ python -c "import syndesi; print(syndesi.__version__)"
   0.8.0

Start a device to talk to
-------------------------

Real devices come later. For now, an *echo server* will do: it sends back everything
it receives. Save this as ``echo_server.py``:

.. code-block:: python
   :caption: echo_server.py

   import socketserver

   class Echo(socketserver.StreamRequestHandler):
       def handle(self):
           while data := self.request.recv(1024):
               self.request.sendall(data)

   with socketserver.ThreadingTCPServer(("127.0.0.1", 4242), Echo) as server:
       print("Echo server on 127.0.0.1:4242")
       server.serve_forever()

Run it in the first terminal and leave it running:

.. code-block:: console

   $ python echo_server.py
   Echo server on 127.0.0.1:4242

Send and receive
----------------

In the second terminal, open a Python prompt and create an **adapter**: the object that
carries bytes to a device. Our server speaks TCP, so the adapter is ``IP``:

.. code-block:: python

   >>> from syndesi import IP
   >>> device = IP("127.0.0.1", 4242)

Nothing has been sent yet. The connection opens by itself on the first operation.
Write something:

.. code-block:: python

   >>> device.write(b"Hello\n")

Now read the answer:

.. code-block:: python

   >>> device.read()
   b'Hello\n'

The server echoed our message. Notice the ``b`` in front of the strings: adapters work
with ``bytes``, exactly what travels on the wire.

Ask a question
--------------

Writing then reading is so common that it has its own method, ``query``:

.. code-block:: python

   >>> device.query(b"How are you?\n")
   b'How are you?\n'

``query`` does a bit more than ``write`` + ``read``: it ignores anything that arrived
*before* the question, so you always get the answer to what you just asked.

How does Syndesi know the answer is complete?
---------------------------------------------

Data on a network can arrive in several pieces. Syndesi waits for the answer, then
considers it finished when nothing new has come for a short time (200 ms for ``IP``).
That rule is called a **stop condition**.

You can choose a better one. Our messages end with ``\n``, so let's stop there:

.. code-block:: python

   >>> from syndesi import Termination
   >>> device = IP("127.0.0.1", 4242, stop_conditions=Termination(b"\n"))
   >>> device.query(b"Faster!\n")
   b'Faster!\n'

The answer comes back as soon as the ``\n`` arrives, without waiting for silence.

Work with text
--------------

Handling ``\n`` and ``bytes`` by hand gets tedious. A **protocol** sits on top of an
adapter and does it for you. ``Delimited`` adds the terminator when writing, removes it
when reading, and converts to ``str``:

.. code-block:: python

   >>> from syndesi import Delimited
   >>> text = Delimited(IP("127.0.0.1", 4242))
   >>> text.query("Hello again")
   'Hello again'

No ``b``, no ``\n``: you are now working with plain strings.

Clean up
--------

Close the connection when you are done:

.. code-block:: python

   >>> text.close()

Or let a ``with`` block do it for you:

.. code-block:: python

   with Delimited(IP("127.0.0.1", 4242)) as text:
       print(text.query("Bye"))

You can stop the echo server with :kbd:`Ctrl+C`.

What you learned
----------------

- An **adapter** (``IP``) moves ``bytes`` to and from a device.
- ``write``, ``read`` and ``query`` are the three everyday methods.
- A **stop condition** decides when a message is complete.
- A **protocol** (``Delimited``) turns raw bytes into something nicer to use.

.. container:: sd-text-right

   :doc:`Next: control an instrument with SCPI → <scpi-instrument>`
