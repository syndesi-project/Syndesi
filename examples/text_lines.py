"""Exchange text lines, the "\n" is added and removed for you. Start echo_server.py first"""

from syndesi import IP, Delimited

with Delimited(IP("127.0.0.1", 4242)) as device:
    print(device.query("Hello"))  # 'Hello'
