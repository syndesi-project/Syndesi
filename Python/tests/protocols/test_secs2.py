from syndesi.protocols.secs2 import *

def test_secs2_format():
    # Test SECS2 - SML message formatting

    ascii = DIAscii('test abc\n ABC \n ')
    assert str(ascii) == '<A "test abc" 0x0A " ABC " 0x0A " ">'



    lst = DIList([
        DIInt(12, 2),
        DIUInt(100, 1),
        DIList([
            DIAscii('START'),
            DIBinary(b'\x12')
        ])
    ])

    print(lst)
