import logging
import os
import pty
import re
import threading
import tty
from contextlib import ExitStack
from selectors import EVENT_READ
from selectors import DefaultSelector as Selector
import time
from multiprocessing.connection import wait
from typing import List, Tuple

# This is a copy of the implementation of PyVirtualSerialPorts
# A copy was made because the print isn't very well suited to get back ports in a thread

#TODO : Finish the serial delayer and make the tests works (they will need to be fixed and the ';' added at the end all the time and also remove the \n)

SEQUENCE_DELIMITER = b';'
DATA_DELAY_DELIMITER = b','
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
        self._fd = open(self._master, "r+b", buffering=0)

        self._r_stop, self._w_stop = os.pipe()

        self._thread = threading.Thread(
            target=self._serial_thread, args=(self._master, self._fd, self._r_stop)
        )
        self._thread.start()

    def port(self):
        return self._slave_name

    def stop(self):
        os.write(self._w_stop, b"\x00")
        self._thread.join()

    def _serial_thread(self, serial_master, writer_fd, stop):
        DELAY_PATTERN = b"([\\w\\d*]+),([0-9]+)"

        sequences : List[Tuple[bytes, float]]= []

        read_buffer = b''

        while True:
            if len(sequences) == 0:
                timeout = None
            else:
                timeout = min([s[1] for s in sequences]) - time.time()
                if timeout < 0:
                    timeout = 0

            ready = wait([writer_fd, stop], timeout=timeout)
            t = time.time()

            if len(ready) == 0:
                # Timeout event
                while True:
                    if len(sequences) == 0:
                        break
                    if sequences[0][1] <= t:
                        writer_fd.write(sequences[0][0])
                        sequences.pop(0)
                    else:
                        break

            if stop in ready:
                break

            if writer_fd in ready:
                read_buffer += writer_fd.read()
                t = time.time()
                # Parse the buffer
                while SEQUENCE_DELIMITER in read_buffer:
                    p = read_buffer.index(SEQUENCE_DELIMITER)
                    sequence_buffer, read_buffer = read_buffer[:p], read_buffer[p+1:]
                    
                    # Parse the sequence
                    data, delay = sequence_buffer.split(DATA_DELAY_DELIMITER)
                    sequences.append((data, t + float(delay) / 1e3))
                    sequences.sort(key=lambda x : x[1])



        # with Selector() as selector, ExitStack() as stack:
        #     stack.enter_context(writer_fd)
        #     selector.register(serial_master, EVENT_READ)
        #     selector.register(stop, EVENT_READ)

        #     data: bytes
        #     data = b""
        #     while loop:
        #         for key, events in selector.select():
        #             if key.fileobj == stop:
        #                 loop = False
        #                 break
        #             if not events & EVENT_READ:
        #                 continue

        #             data += writer_fd.read()

        #             if len(data) > 0:
        #                 data = data.replace(b"\n", b";")
        #                 while b";" in data:
        #                     # There is a fragment
        #                     fragment, data = data.split(b";", 1)
        #                     match = re.match(DELAY_PATTERN, fragment)
        #                     payload = match.group(1)
        #                     delay = int(match.group(2)) / 1000
        #                     logging.debug(
        #                         f"Sending {payload} after {delay * 1e3:.1f} ms"
        #                     )
        #                     sleep(delay)
        #                     writer_fd.write(payload)

#TODO : Change the serial delayer so that each time is relative to the moment the command was sent and not relative to each other
