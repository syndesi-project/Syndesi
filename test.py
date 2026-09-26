from syndesi import IP

def main():
    adapter = IP('tcpbin.com', port=4242)

    response = adapter.query(b'test\n')

    print(f'Response : {response}')

if __name__ == '__main__':
    main()