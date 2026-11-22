"""
A device to talk to : sends back everything it receives, on 127.0.0.1:4242

Run it first, in its own terminal, for ip_query.py, text_lines.py, ...
"""

import threading

from syndesi import FragmentSC, IPServer
from syndesi.errors import AdapterDisconnectedError


def echo(client):
    with client:
        try:
            while True:
                client.write(client.read(timeout=None))
        except AdapterDisconnectedError:
            pass  # the client left


server = IPServer("127.0.0.1", 4242, stop_conditions=[FragmentSC()])
print("Echo server on 127.0.0.1:4242, Ctrl+C to stop")
while True:
    client = server.read()  # waits for a connection, returns an IP adapter
    threading.Thread(target=echo, args=(client,), daemon=True).start()
