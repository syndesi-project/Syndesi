Protocols
=========

Protocols in Syndesi define data formatting for device communication on top of adapters.

**Available Protocols:**
- **Delimited**: Adds delimiters to commands, useful for text-based communication.
- **SCPI**: Supports the SCPI standard used by many lab instruments.
- **Modbus**: Implements the Modbus RTU/TCP protocol for industrial automation devices.

**Example Usage:**

```python
from syndesi.adapters import SerialPort
from syndesi.protocols import Modbus

# Set up a Modbus protocol over a serial connection
device = SerialPort("/dev/ttyUSB0", baudrate=9600)
modbus_protocol = Modbus(device)
response = modbus_protocol.read_holding_registers(1, 10)
print(response) 