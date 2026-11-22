Drivers
=======

Base classes for your own drivers. Guides: :doc:`/tutorials/first-driver`,
:doc:`/how-to/write-a-driver`.

.. autoclass:: syndesi.drivers.driver.Driver
   :members: open, close, test
   :no-show-inheritance:

.. autoclass:: syndesi.drivers.driver.SubDriver
   :no-members:
   :no-show-inheritance:

.. autoclass:: syndesi.drivers.scpi_driver.SCPIDriver
   :members: get_identification, get_system_error, get_system_version,
             clear_status_registers, trigger, reset
   :no-show-inheritance:

.. autoclass:: syndesi.drivers.tools.FlexibleEnum
   :members: label
   :no-show-inheritance:
