Adapters
========

Adapters are the base communication layer in Syndesi, allowing connection to devices using specific communication types.

**Available Adapters:**
- **IP**: Connects to devices over a TCP/IP or UDP/IP network.
- **SerialPort**: Allows serial communication with devices.
- **VISA**: Supports VISA-compatible instruments.

Each adapter inherits from the base `Adapter` class and provides methods for connecting, sending, and receiving data.

**Example Usage:**

```python
from syndesi.adapters import IP

# Initialize an IP adapter
device = IP("192.168.1.10", port=5025)
device.write(b"*IDN?")
response = device.read()
print(response)