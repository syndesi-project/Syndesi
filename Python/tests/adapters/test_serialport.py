from time import sleep
from syndesi.adapters import SerialPort
from syndesi.adapters.stop_conditions import *

SEQUENCE = [
    (0.25, b'ABCDE'),
    (0.1, b'FGHIJ'),
    (0.5, b'KLMNO'),
    (1, b'PQRST'),
    (1, b'UVWXYZ')
]

TIME_DELTA = 1e-3
CLIENT_SEQUENCE = b'x'
TIME_PER_BYTE = 0.1
PORT = '/dev/ttyACM1'
BAUDRATE = 115200

# Test response timeout
# long enough to catch the first sequence

def test_response_A():

    # This should catch the first sequence
    sleep(0.1)
    client = SerialPort(
        port=PORT,
        baudrate=BAUDRATE,
        timeout=1,
        stop_condition=None#Timeout(response=SEQUENCE[0][0] + TIME_DELTA,continuation=0.01)
        )
    client.write(CLIENT_SEQUENCE)
    data = client.read()
    while True:
        if b'Z' in client.read(timeout=3):
            break

    assert data == SEQUENCE[0][1]

    client.close()



# # Test response timeout
# # not long enough to catch the first sequence

# def test_response_B():
#     thread = Thread(target=server_thread, daemon=True)
#     thread.start()
#     # This sould not    
#     sleep(0.1)
#     client = IP(
#         HOST,
#         port=PORT,
#         stop_condition=Timeout(response=SEQUENCE[0][0] - TIME_DELTA,
#         continuation=0.01))
#     client.write(CLIENT_SEQUENCE)
#     data = client.read()
#     client.close()
#     assert data == b''
#     thread.join()

# # Test continuation timeout
# # Long enough to catch the first two sequences

# def test_continuation():
#     thread = Thread(target=server_thread, daemon=True)
#     thread.start()
#     # This sould not    
#     sleep(0.1)
#     client = IP(
#         HOST,
#         port=PORT,
#         stop_condition=Timeout(response=SEQUENCE[0][0] + TIME_DELTA,
#         continuation=SEQUENCE[1][0] + TIME_DELTA))
#     client.write(CLIENT_SEQUENCE)
#     data = client.read()
#     client.close()
#     assert data == SEQUENCE[0][1] + SEQUENCE[1][1]
#     thread.join()

# # Test total timeout
# # This should be long enough to catch the first three sequences

# def test_total_A():
#     thread = Thread(target=server_thread, daemon=True)
#     thread.start()
#     # This sould not    
#     sleep(0.1)
#     client = IP(
#         HOST,
#         port=PORT,
#         stop_condition=Timeout(response=SEQUENCE[0][0] + TIME_DELTA,
#             continuation=10,
#             #total=sum(s[0] + TIME_DELTA for s in SEQUENCES[:3]))
#             total=sum(s[0] + TIME_DELTA for s in SEQUENCE[:3])
#         )
#         )
#     client.write(CLIENT_SEQUENCE)
#     data = client.read()
#     client.close()
#     assert data == b''.join(s[1] for s in SEQUENCE[:3])
#     thread.join()

# # Test termination
# def test_termination_A():
#     thread = Thread(target=server_thread, daemon=True)
#     thread.start()
#     # This sould not
#     sleep(0.1)
#     client = IP(
#         HOST,
#         port=PORT,
#         stop_condition=Termination(b'F')
#         )
#     client.write(CLIENT_SEQUENCE)
#     data = client.read()
#     client.close()
#     complete_sequence = b''.join(s[1] for s in SEQUENCE)
#     assert data == complete_sequence[:complete_sequence.index(b'F')+1]
#     thread.join()


# # Test length
# def test_length():
#     thread = Thread(target=server_thread, daemon=True)
#     thread.start()
#     # This sould not
#     sleep(0.1)
#     client = IP(
#         HOST,
#         port=PORT,
#         stop_condition=Length(10)
#         )
#     client.write(CLIENT_SEQUENCE)
#     data = client.read()
#     client.close()
#     complete_sequence = b''.join(s[1] for s in SEQUENCE)
#     assert data == complete_sequence[:10]
#     thread.join()

