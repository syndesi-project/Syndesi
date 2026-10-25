"""
ip_server.py

Creates an IP server, IP clients, and exchanges data between them
"""
from syndesi import IP, IPServer

ADDRESS = '127.0.0.1'
PORT = 4242

DATA = "Syndesi"

def main():
    print(f'Open IP server on {ADDRESS}:{PORT}')
    server = IPServer(ADDRESS, PORT, auto_open=True)

    print(f'Connect IP client to {ADDRESS}:{PORT}')
    client = IP(ADDRESS, PORT, auto_open=True)

    client_server = server.read()
    print(f'Server received client (port : {client_server.descriptor.port})')

    client.write(DATA)

    data = client_server.read()
    client_server.write(data)

    data_out = client.read()
    print(data_out)

if __name__ == '__main__':
    main()