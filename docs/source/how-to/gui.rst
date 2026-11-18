Use the graphical bench
=======================

``syndesi ui`` lets you assemble adapters, protocols and drivers, then call their
methods and watch the traffic, without writing a line of code.

Install and start
-----------------

.. code-block:: console

   $ pip install "syndesi[ui]"
   $ syndesi ui

Build a stack
-------------

The first screen has three panels:

- **Library**: the components you can use, adapters, protocols and drivers.
- **Stack**: drag a component here. Its slots (the parameters that expect another
  component) appear under it, and only accept what fits. Or click the ``+`` of a slot.
- **Inspector**: the parameters of the selected component, with forms generated from
  their types.

The Python code of your stack is shown at the bottom, ready to copy into a script.

Test it
-------

The second screen opens the stack and lists every object in it: the top component,
the protocol a driver built for itself, the adapter below, sub-drivers… Select one to:

- run its methods from a form, and see the result;
- send raw data and read answers (*I/O* tab);
- follow every command, write, read and event in the log.

Add your own drivers
--------------------

.. code-block:: console

   $ syndesi ui -l power_supply.py              # every class of the file
   $ syndesi ui -l power_supply.py:PowerSupply  # ...and put PowerSupply on the stack
   $ syndesi ui -l mycompany.drivers            # every class of an installed module

``-l`` can be repeated. The forms come from your code: type hints decide the editor
(number, text, checkbox, list of choices for an ``Enum``…) and numpy-style docstrings
give the descriptions. A well-documented driver needs no extra work.

Save and reopen
---------------

Save the stack from the window, then reopen it later:

.. code-block:: console

   $ syndesi ui my_bench.json

Change the theme
----------------

.. code-block:: console

   $ syndesi ui --theme dark      # auto (follows the system), light or dark
