"""Read and write a Modbus TCP device. Start modbus_device.py first"""

from syndesi import IP, Modbus

plc = Modbus(IP("127.0.0.1", 5020))  # the standard port is 502

print(plc.read_holding_registers(1, 2))  # [1234, 42]
plc.write_single_register(2, 500)
print(plc.read_single_register(2))  # 500
print(plc.read_coils(1, 4))  # [False, False, True, False]

plc.close()
