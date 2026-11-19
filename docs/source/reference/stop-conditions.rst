Stop conditions
===============

Stop conditions decide when the bytes received form a complete frame. Guide:
:doc:`/how-to/framing`. Concepts: :doc:`/explanation/frames`.

.. code-block:: python

   from syndesi import Continuation, FragmentSC, Length, Termination, Total

.. autoclass:: syndesi.adapters.stop_conditions.Termination
   :no-members:
   :no-show-inheritance:

.. autoclass:: syndesi.adapters.stop_conditions.Length
   :no-members:
   :no-show-inheritance:

.. autoclass:: syndesi.adapters.stop_conditions.Continuation
   :no-members:
   :no-show-inheritance:

.. autoclass:: syndesi.adapters.stop_conditions.Total
   :no-members:
   :no-show-inheritance:

.. autoclass:: syndesi.adapters.stop_conditions.FragmentSC
   :no-members:
   :no-show-inheritance:
