Experimental Features
=====================

This section covers experimental features in Syndesi, such as the API and shell, which are subject to change.

**API and Shell Usage:**

The Syndesi API provides an interface for scripting and interacting with devices programmatically.

**Example:**
```python
from syndesi.api import DeviceAPI

api = DeviceAPI()
api.connect("192.168.1.10", protocol="SCPI")
response = api.query("*IDN?")
print(response)