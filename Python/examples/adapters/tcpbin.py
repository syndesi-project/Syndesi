from syndesi.adapters import IP

# Settings
ADDRESS = 'tcpbin.com'
PORT = 4242
DATA = 'Hello World\n'

def main():
    print(f"Opening IP adapter to {ADDRESS}:{PORT} ...", end='')
    # Open the adapter
    adapter = IP(ADDRESS, port=PORT)
    print(f"Sending  : {repr(DATA)}...")
    # Send data and wait for response
    received = adapter.query(DATA)
    print(f"Received : {repr(received)}")

if __name__ == '__main__':
    main()