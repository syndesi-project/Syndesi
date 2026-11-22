Command line
============

Installing Syndesi adds two commands: ``syndesi`` and ``syndesi-trace``.

``syndesi``
-----------

.. code-block:: text

   syndesi [-h] [--version] [-v] [-q] {term,ui}

==================  =====================================
``-v``, ``-vv``     log level INFO, DEBUG
``-q``              quiet, critical errors only
``--version``       print the version
==================  =====================================

``syndesi term``
~~~~~~~~~~~~~~~~

Interactive terminal. Guide: :doc:`/how-to/terminal`.

.. code-block:: text

   syndesi term ip      ADDRESS PORT [--protocol {TCP,UDP}]  [options]
   syndesi term serial  PORT BAUDRATE [--rtscts] [--list]   [options]
   syndesi term i2c     BUS ADDRESS [--read N] [--list]     [options]
   syndesi term spi     DEVICE [--list]                     [options]
   syndesi term visa    DESCRIPTOR                          [options]

=============================  =================================================  ===========
Option                         Effect                                             Default
=============================  =================================================  ===========
``-t``, ``--timeout SECONDS``  time to wait for an answer                         ``2``
``--term TERM``                line ending added to each command:                 ``lf``
                               ``cr``, ``lf``, ``crlf`` or any string
``-f``, ``--format FORMAT``    ``bytes`` (Python ``b'...'`` notation),            ``bytes``
                               ``hex``, or ``raw`` text
``--protocol {TCP,UDP}``       IP only                                            ``TCP``
``--rtscts``                   serial only, hardware flow control                 off
``--list``                     serial, i2c, spi: list ports or buses and exit
=============================  =================================================  ===========

``syndesi ui``
~~~~~~~~~~~~~~

Graphical bench, needs ``pip install "syndesi[ui]"``. Guide: :doc:`/how-to/gui`.

.. code-block:: text

   syndesi ui [STACK.json] [-l SOURCE]... [--theme {auto,light,dark}]

=============================  ==========================================================
``STACK.json``                 open a saved stack
``-l``, ``--load SOURCE``      add components to the library: ``file.py``,
                               ``file.py:Class`` (also puts it on the stack), a folder,
                               a module or a package name. Repeatable.
``--theme``                    ``auto`` (follows the system, default), ``light``, ``dark``
=============================  ==========================================================

``syndesi-trace``
-----------------

Live viewer of the traffic of every Syndesi adapter on this machine. Guide:
:doc:`/how-to/debugging`.

.. code-block:: text

   syndesi-trace [--flat] [--filter PATTERN] [--time {rel,abs}] [--no-frag]
                 [--max-events N] [--output FILE] [--port PORT] [--group GROUP]

=========================  ==============================================================  ==================
Option                     Effect                                                          Default
=========================  ==============================================================  ==================
``--flat``                 one line per event instead of the interactive view with tabs
``--filter PATTERN``       only adapters matching this pattern (``*`` and ``?``)           ``*``
``--time {rel,abs}``       time relative to the adapter's opening, or absolute             ``rel``
``--no-frag``              hide fragments, show frames only
``--max-events N``         events kept per adapter in interactive mode, ``0`` = no limit
``--output FILE``          write the flat output to a file
``--port PORT``            UDP port                                                        ``12000``
``--group GROUP``          multicast group                                                 ``239.255.42.99``
=========================  ==============================================================  ==================
