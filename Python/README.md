# Syndesi Python

The Syndesi Python package provides the user with the necessary tools to control compatible devices

- drivers : device-specific implementation
- parsers : mid-level frame parsing
- communication wrapper (wrappers) : Wrappers for low-level communication (TCP, UDP, UART, etc...)
  - IP (TCP / UDP)
  - UART
  - USB (?)


## Notes

The user could specify the wrapper directly (IP, UART, etc...)

```python

mydevice = Device(IP("182.168.1.12"))
```

This assumes that the choice of the wrapper is trivial for the user.

