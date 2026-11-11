# File : fake_psu.py
# Author : Sébastien Deriaz
# License : GPL
"""
A fake SCPI power supply on TCP, for demo_psu.py and the GUI

    python examples/drivers/fake_psu.py [port]      (5025 by default)

Commands end with \\n and can be chained with ';' :
*IDN?  SYST:ERR?  INST:NSEL <n>  VOLT <v>  VOLT?  MEAS:VOLT?  OUTP ON|OFF  OUTP?
"""

import random
import socketserver
import sys


class FakePSU(socketserver.StreamRequestHandler):
    """One connection"""

    def setup(self) -> None:
        super().setup()
        self.channel = 1
        self.voltage = {1: 0.0, 2: 0.0}
        self.output = {1: False, 2: False}

    def handle(self) -> None:
        for raw in self.rfile:
            answers = []
            for command in raw.decode().strip().split(";"):
                answer = self.execute(command.strip().upper())
                if answer is not None:
                    answers.append(answer)
            if answers:
                self.wfile.write((";".join(answers) + "\n").encode())

    def execute(self, command: str) -> str | None:
        """Answer one command, None if it has no answer"""
        name, _, argument = command.partition(" ")
        if name == "*IDN?":
            return "Syndesi,DemoPSU,0001,1.0"
        if name == "SYST:ERR?":
            return '0,"No error"'
        if name == "INST:NSEL":
            self.channel = int(argument)
        elif name == "VOLT":
            self.voltage[self.channel] = float(argument)
        elif name == "VOLT?":
            return f"{self.voltage[self.channel]:.3f}"
        elif name == "MEAS:VOLT?":
            measured = self.voltage[self.channel] if self.output[self.channel] else 0.0
            return f"{measured + random.uniform(-0.002, 0.002):.4f}"
        elif name == "OUTP":
            self.output[self.channel] = argument == "ON"
        elif name == "OUTP?":
            return "1" if self.output[self.channel] else "0"
        return None


class Server(socketserver.ThreadingTCPServer):
    """Accepts several connections"""

    allow_reuse_address = True
    daemon_threads = True


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5025
    with Server(("127.0.0.1", port), FakePSU) as server:
        print(f"Fake power supply listening on 127.0.0.1:{port}")
        server.serve_forever()
