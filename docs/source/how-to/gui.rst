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

- **Library**: the components you can use, adapters, protocols and drivers, one tab
  per collection (see below).
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

The library
-----------

The library has one tab per collection:

- **Syndesi**: the adapters, protocols and drivers of Syndesi, grouped by layer.
- **syndesi-drivers**: ready-made drivers for lab instruments and industrial I/O, loaded
  at startup when the package is installed (``pip install syndesi-drivers``). Grayed
  out otherwise, the tab says how to install it.
- One tab per **package** or **folder** you load, grouped by sub-package or file.
- **Files**: the files and modules loaded one by one.

A stack mixes collections, a driver of ``syndesi-drivers`` on an ``IP`` of Syndesi for
instance. When you select a slot, the library moves to a tab that has something for it.
A search lists the other tabs that match, as links.

When the tabs don't all fit, the ``+N`` menu next to them lists every collection.

Add your own drivers
--------------------

Use **Load** in the library, or ``-l`` on the command line:

.. code-block:: console

   $ syndesi ui -l power_supply.py              # every class of the file
   $ syndesi ui -l power_supply.py:PowerSupply  # ...and put PowerSupply on the stack
   $ syndesi ui -l ./my_drivers                 # every file of a folder
   $ syndesi ui -l mycompany.drivers            # every module of a package

``-l`` can be repeated. The forms come from your code: type hints decide the editor
(number, text, checkbox, list of choices for an ``Enum``…) and numpy-style docstrings
give the descriptions. A well-documented driver needs no extra work.

Loading a folder or a package imports a lot of code, so it is careful:

- tests and examples (``test_*.py``, ``example_*.py``, ``tests/``, ``examples/``) and
  virtual environments are left out;
- in a folder, a file that runs code when imported (a call, a loop, a ``with`` at the
  top level: a script) is skipped. Load it alone with **Load → Python file…** if it
  is safe;
- a module that fails to import doesn't stop the others. The tab says what went wrong,
  under *details*.

A folder with an ``__init__.py`` is a package: its modules are loaded the same way as
an installed package's.

Save and reopen
---------------

Save the stack from the window, then reopen it later:

.. code-block:: console

   $ syndesi ui my_bench.json

Change the theme
----------------

.. code-block:: console

   $ syndesi ui --theme dark      # auto (follows the system), light or dark
