Error Handling
==============

This section describes errors raised by the Syndesi package

- `RuntimeError` : Raised in case of invalid configuration at runtime (timeout not configured, missing arguments, etc...)
- `ValueError` : Raised in case of incompatible arguments
- `SyndesiError` : Syndesi error base class

    - `AdapterDisconnected` : Raised when the adapter loses connection to the device
    - `AdapterTimeoutError` : Raised if a timeout occurs, meaning the device did not response within the given timeframe

**Common Errors:**

- `TimeoutError`: Raised if a device fails to respond within the specified timeout.
- `AdapterDisconnected`: Occurs when the adapter loses connection to the device.