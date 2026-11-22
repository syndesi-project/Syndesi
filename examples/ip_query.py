"""Send bytes over TCP and read the answer. Start echo_server.py first"""

from syndesi import IP

device = IP("127.0.0.1", 4242)

device.write(b"Hello\n")
print(device.read())  # b'Hello\n'

print(device.query(b"How are you?\n"))  # write, then read the answer

device.close()
