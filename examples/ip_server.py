"""
ip_server.py

Creates an IP server, IP clients, and exchanges data between them
"""
from syndesi import IP, IPServer, Termination

ADDRESS = '127.0.0.1'
PORT = 4242

DATA = b"Syndesi\n"

def main():
    # Create the server
    # Give a "\n" stop-condition speed up the exchange
    print(f'[Server] Open IP server on {ADDRESS}:{PORT}')
    server = IPServer(ADDRESS, PORT, stop_conditions=[Termination("\n")])

    # Create the client
    print(f'[Client] Connect IP client to {ADDRESS}:{PORT}')
    client = IP(ADDRESS, PORT, stop_conditions=[Termination("\n")])

    # Receive the client adapter on the server side
    client_handle = server.read()
    print(f'[Server] Server received client (port : {client_handle.descriptor.port})')

    # Send data from the client to the server
    print(f'[Client] Sending {DATA}')
    client.write(DATA)

    # Receive data on the server side, echo it back
    data = client_handle.read()
    print(f'[Server] Received {data}, echoing back to client')
    client_handle.write(data)

    # Read the echoed back on the client side
    data_out = client.read()
    print(f'[Client] Received {data_out} back')

if __name__ == '__main__':
    main()