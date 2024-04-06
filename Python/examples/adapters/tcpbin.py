from syndesi.adapters import IP
from syndesi.tools.logger import GlobalLogger

# Settings
ADDRESS = 'tcpbin.com'
PORT = 4242
DATA = b'Hello World\n'

def main():
    print(f"Opening IP adapter to {ADDRESS}:{PORT} ...")
    # Open the adapter
    adapter = IP(ADDRESS, port=PORT)
    print(f"Sending  : {repr(DATA)}...")
    # Send data and wait for response
    received = adapter.query(DATA)
    print(f"Received : {repr(received)}")


    # temp
    gl = GlobalLogger()
    print(gl._log)

if __name__ == '__main__':
    main()