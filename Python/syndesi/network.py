# Syndesi network
#
# Sébastien Deriaz
# 14.11.2022

import socket
from .frame import OutboundFrame, InboundFrame

class Network:
    def __init__(self):
        """
        Syndesi Network instance
        """


    def request(self, requestFrame : OutboundFrame):
        """
        Send the provided frame

        Parameters
        ----------
        frame : Frame
        """

        PSDU = requestFrame.data()
        #print(f"Sending frame {PSDU}")

        # TODO : Add protocol check (only IP for now)
        # TODO : Change IP address
        HOST = "192.168.1.67"
        PORT = 2608

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((HOST, PORT))
            s.sendall(PSDU)
            confirm_data = s.recv(1024)
            return InboundFrame(confirm_data, requestFrame)
        
        return None

network = Network()