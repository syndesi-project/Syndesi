Control an instrument with SCPI
===============================

Most lab instruments (power supplies, multimeters, oscilloscopes, signal generators…)
understand **SCPI**, a standard set of text commands. In this tutorial you will drive a
simulated two-channel power supply: identify it, set a voltage, switch it on and
measure its output.

.. rubric:: What you need

Syndesi installed (see :doc:`first-connection`) and the simulated power supply,
:download:`fake_psu.py <../../../examples/drivers/fake_psu.py>`, from the Syndesi
repository.

Start the power supply
----------------------

In a first terminal:

.. code-block:: console

   $ python fake_psu.py
   Fake power supply listening on 127.0.0.1:5025

It listens on port 5025, the usual port for SCPI over a network.

Say hello
---------

In a second terminal, open Python:

.. code-block:: python

   >>> from syndesi import IP, SCPI
   >>> psu = SCPI(IP("127.0.0.1"))
   >>> psu.query("*IDN?")
   'Syndesi,DemoPSU,0001,1.0'

Every SCPI instrument answers ``*IDN?`` with its maker, model, serial number and
firmware version.

Notice what you did *not* write: no port, no ``\n``, no ``bytes``. ``SCPI`` knows that
instruments listen on port 5025 and that commands end with a newline. You only give
what differs from those defaults.

Set a voltage
-------------

Commands that don't expect an answer are sent with ``write``:

.. code-block:: python

   >>> psu.write("VOLT 3.3")
   >>> psu.query("VOLT?")
   '3.300'

Answers are always strings. Convert them when you need a number:

.. code-block:: python

   >>> float(psu.query("VOLT?"))
   3.3

Switch on and measure
---------------------

.. code-block:: python

   >>> psu.write("OUTP ON")
   >>> float(psu.query("MEAS:VOLT?"))
   3.2994

The measured value moves a little at each call, like a real one would.

Select another channel
----------------------

Our power supply has two outputs. ``INST:NSEL`` selects the one the next commands apply
to, and ``;`` chains several commands on one line:

.. code-block:: python

   >>> psu.write("INST:NSEL 2;VOLT 12;OUTP ON")
   >>> psu.query("INST:NSEL 2;MEAS:VOLT?")
   '12.0013'

Check for errors
----------------

Instruments keep a queue of errors. Reading it after a sequence of commands is a good
habit:

.. code-block:: python

   >>> psu.query("SYST:ERR?")
   '0,"No error"'

When nobody answers
-------------------

Ask a question the instrument doesn't know, and nothing comes back. Syndesi waits for
the adapter's timeout (1 s for ``IP``), then raises an error rather than blocking
forever:

.. code-block:: python

   >>> psu.query("UNKNOWN?")
   Traceback (most recent call last):
     ...
   syndesi.tools.errors.AdapterTimeoutError: No response received from target within 1.0 seconds

Some measurements take longer than a second. Give the adapter a longer timeout:

.. code-block:: python

   >>> psu = SCPI(IP("127.0.0.1", timeout=10))

Switch off
----------

.. code-block:: python

   >>> psu.write("OUTP OFF")
   >>> psu.close()

What you learned
----------------

- ``SCPI`` wraps an adapter and fills in the port and terminator instruments expect.
- ``write`` sends a command, ``query`` asks a question and returns the answer as a
  string.
- A missing answer raises ``AdapterTimeoutError`` after the adapter's timeout.

Typing SCPI strings is fine in a prompt, but a test script deserves better than
``psu.write("INST:NSEL 2;VOLT 12")``. Let's give the power supply real methods.

.. container:: sd-text-right

   :doc:`Next: write your first driver → <first-driver>`
