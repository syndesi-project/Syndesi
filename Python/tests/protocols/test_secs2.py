from syndesi.protocols.secs2 import *

def test_secs2_format():
    # Test SECS2 - SML message formatting

    # Make one huge DataItem with everything in it

    dataitem = DIList([
        DIList([
            DIInt(0, 8),
            DIList([
                DIAscii(),
                DIBinary(),
                DIBoolean(),
                DIFloat(size=4),
                DIInt(size=8),
                DIUInt(size=1)     
            ])
        ]),
        DIAscii(''),
        DIAscii("1234 test \n123\n ABC"),
        DIBinary(b'\x12'),
        DIBoolean(True),
        DIFloat(1.1234, 4),
        DIInt(-12, 2),
        DIUInt(15, 4)
    ])

    dataitem_string = str(dataitem)

    print(dataitem_string)

    encoded_dataitem = dataitem.encode()

    decoded_dataitem = decode_dataitem(encoded_dataitem)

    print(decoded_dataitem)