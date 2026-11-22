"""Decide where a message ends. Start echo_server.py first"""

from syndesi import IP, Length, Termination

# Done as soon as "\n" arrives, instead of waiting for the line to go quiet
device = IP("127.0.0.1", 4242, stop_conditions=Termination(b"\n"))
print(device.query(b"Fast answer\n"))  # b'Fast answer\n'

# Exactly 4 bytes per message, the rest waits for the next read
device.set_stop_conditions(Length(4))
print(device.query(b"ABCDEFGH"))  # b'ABCD'
print(device.read())  # b'EFGH'

device.close()
