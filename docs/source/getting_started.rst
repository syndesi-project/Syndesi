Getting Started
===============

This section introduces the basics of using Syndesi.

**Installation:**

To install Syndesi, use the following:

pip install syndesi

**Quickstart Example:**

```python
from syndesi.adapters import IP
from syndesi.protocols import Delimited

# Connect to a device over IP
device = IP("192.168.1.10", port=80)

# Use a Delimited protocol for communication
protocol = Delimited(device, termination="\n")
protocol.write("COMMAND")
response = protocol.read()
print("Response:", response)```


Refer to the Adapters and Protocols sections for more details on configuring specific settings.



