from contextlib import ExitStack
import os
import pty
from selectors import DefaultSelector as Selector, EVENT_READ
import sys
import tty
import threading
import re
from time import sleep, time
import logging

# This is a copy of the implementation of PyVirtualSerialPorts
# A copy was made because the print isn't very well suited to get back ports in a thread

class SerialDelayer:
    def __init__(self) -> None:
        """
        Generate 2 virtual serial ports that forward their data to each other.
        """
        self._stop = [False]

        self._master, self._slave = pty.openpty()
        tty.setraw(self._master)
        os.set_blocking(self._master, False)
        self._slave_name = os.ttyname(self._slave)
        self._fd = open(self._master, 'r+b', buffering=0)

        self._r_stop, self._w_stop = os.pipe()
            
        self._thread = threading.Thread(target=self._serial_thread, args=(self._master, self._fd, self._r_stop))
        self._thread.start()
    
    def port(self):
        return self._slave_name

    def stop(self):
        os.write(self._w_stop, b'\x00')
        self._thread.join()

    def _serial_thread(self, master, writer_fd, stop):
        DELAY_PATTERN = b'([\\w\\d*]+),([0-9]+)'

        loop = True
        with Selector() as selector, ExitStack() as stack:
            stack.enter_context(writer_fd)
            selector.register(master, EVENT_READ)
            selector.register(stop, EVENT_READ)

            data : bytes
            data = b''
            while loop:
                for key, events in selector.select():
                    if key.fileobj == stop:
                        loop = False
                        break
                    if not events & EVENT_READ:
                        continue
                    
                    data += writer_fd.read()

                    if len(data) > 0:
                        data = data.replace(b'\n', b';')
                        while b';' in data:
                            # There is a fragment
                            fragment, data = data.split(b';', 1)
                            match = re.match(DELAY_PATTERN, fragment)
                            payload = match.group(1)
                            delay = int(match.group(2)) / 1000
                            logging.debug(f'Sending {payload} after {delay*1e3:.1f} ms')
                            sleep(delay)
                            writer_fd.write(payload)