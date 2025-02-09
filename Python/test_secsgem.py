from syndesi.protocols import Secs2
from syndesi.adapters import IP



def main():
    
    prot = Secs2(IP('127.0.0.1', 5000))



    prot.send()


if __name__ == '__main__':
    main()