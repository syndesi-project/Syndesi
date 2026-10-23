import socketserver
import threading

import pytest

HOST = "127.0.0.1"


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "serial_only: test runs only on serial protocols (Modbus RTU/ASCII for example)")


class _Echo(socketserver.BaseRequestHandler):
    def handle(self):
        while data := self.request.recv(4096):
            self.request.sendall(data)


@pytest.fixture(scope="module")
def port():
    """Port of a TCP server sending back everything it receives"""
    server = socketserver.ThreadingTCPServer((HOST, 0), _Echo)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server.server_address[1]
    server.shutdown()
    server.server_close()
