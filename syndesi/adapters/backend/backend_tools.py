# File : backend_tools.py
# Author : Sébastien Deriaz
# License : GPL
"""
Various tools used in the backend

"""

import socket
from multiprocessing.connection import Connection

BACKEND_REQUEST_DEFAULT_TIMEOUT = 0.5


def get_conn_addresses(conn: Connection) -> tuple[tuple[str, int], tuple[str, int]]:
    """
    Return sock (local) address and peer (remote) address of a multiprocessing Connection

    Parameters
    ----------
    conn : Connection

    Returns
    -------
    sock : tuple
        (address, port)
    peer tuple
        (address, port)
    """
    try:
        fd = conn.fileno()
    except OSError:
        return (("closed", 0), ("closed", 0))

    sock = socket.fromfd(fd, socket.AF_INET, socket.SOCK_STREAM)
    peer_address = sock.getpeername()
    sock_address = sock.getsockname()
    return sock_address, peer_address

class ConnectionDescriptor:
    """
    String description of a multiprocessing Connection
    """
    def __init__(self, conn: Connection) -> None:
        local, remote = get_conn_addresses(conn)
        self._remote_address = remote[0]
        self._remote_port = int(remote[1])
        self._local_address = local[0]
        self._local_port = int(local[1])

    def remote(self) -> str:
        """
        Return remote address in the format 'address:port'
        """
        return f"{self._remote_address}:{self._remote_port}"

    def local(self) -> str:
        """
        Return local address in the format 'address:port'
        """
        return f"{self._local_address}:{self._local_port}"

    def remote_address(self) -> str:
        """
        Return remote ip address
        """
        return self._remote_address

    def remote_port(self) -> int:
        """
        Return remote port
        """
        return self._remote_port

    def local_address(self) -> str:
        """
        Return local ip address
        """
        return self._local_address

    def local_port(self) -> int:
        """
        Return local port
        """
        return self._local_port

    def __str__(self) -> str:
        return f"{self.local()}->{self.remote()}"


class NamedConnection(ConnectionDescriptor):
    """
    Helper class to hold a connection with a name
    """
    def __init__(self, conn: Connection) -> None:
        super().__init__(conn)
        self.conn = conn

    def __str__(self) -> str:
        return f"Connection {self.remote()}"

    def __repr__(self) -> str:
        return self.__str__()
