import socket
from multiprocessing.connection import Connection

BACKEND_REQUEST_DEFAULT_TIMEOUT = 0.5


def get_conn_addresses(conn: Connection) -> tuple[tuple[str, int], tuple[str, int]]:
    try:
        fd = conn.fileno()
    except OSError:
        return (("closed", 0), ("closed", 0))
    else:
        sock = socket.fromfd(fd, socket.AF_INET, socket.SOCK_STREAM)
        # try:
        # TODO : Implement exception
        # address, port = sock.getpeername()  # (IP, port) tuple
        peer_address = sock.getpeername()
        sock_address = sock.getsockname()
        return sock_address, peer_address
        # except Exception:
        #     return (("error", 0), ("closed", 0))


class ConnectionDescriptor:
    def __init__(self, conn: Connection) -> None:
        """
        Description of a multiprocessing Connection
        """
        local, remote = get_conn_addresses(conn)
        self._remote_address = remote[0]
        self._remote_port = int(remote[1])
        self._local_address = local[0]
        self._local_port = int(local[1])

    def remote(self) -> str:
        return f"{self._remote_address}:{self._remote_port}"

    def local(self) -> str:
        return f"{self._local_address}:{self._local_port}"

    def remote_address(self) -> str:
        return self._remote_address

    def remote_port(self) -> int:
        return self._remote_port

    def local_address(self) -> str:
        return self._local_address

    def local_port(self) -> int:
        return self._local_port

    def __str__(self) -> str:
        return f"{self.local()}->{self.remote()}"


class NamedConnection(ConnectionDescriptor):
    def __init__(self, conn: Connection) -> None:
        super().__init__(conn)
        self.conn = conn

    def __str__(self) -> str:
        return f"Connection {self.remote()}"

    def __repr__(self) -> str:
        return self.__str__()
