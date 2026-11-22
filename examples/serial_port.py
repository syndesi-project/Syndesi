"""
Talk to a device on a serial port that answers text lines (an Arduino, ...)

Change PORT and BAUDRATE to match your device
"""

import time

from syndesi import Delimited, SerialPort

PORT = "/dev/ttyUSB0"  # "COM3" on Windows
BAUDRATE = 115200

print("Serial ports :", SerialPort.list_ports())

device = Delimited(SerialPort(PORT, BAUDRATE))
device.open()
time.sleep(2)  # an Arduino restarts when its port opens, give it time to boot

print(device.query("Hello"))
device.close()
