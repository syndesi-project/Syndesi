"""A server and its client in the same script, nothing else to start"""

from syndesi import IP, IPServer

server = IPServer("127.0.0.1", 4243)
server.open()  # listen now, the client connects below

client = IP("127.0.0.1", 4243)
client.open()  # connect now : read() on the server waits for a connection

connection = server.read()  # the client, seen from the server : an IP adapter

client.write(b"Syndesi\n")
data = connection.read()
print("Server received", data)  # b'Syndesi\n'
connection.write(data)
print("Client received", client.read())  # b'Syndesi\n'

client.close()
server.close()
