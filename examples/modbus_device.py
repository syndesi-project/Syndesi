"""A Modbus TCP device on 127.0.0.1:5020, for modbus_client.py"""

from syndesi import IPServer, ModbusServer

device = ModbusServer(IPServer("127.0.0.1", 5020))
device.holding_registers[1] = 1234
device.holding_registers[2] = 42
device.coils[3] = True

print("Modbus device on 127.0.0.1:5020, Ctrl+C to stop")
device.serve_forever()
