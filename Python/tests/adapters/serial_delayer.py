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
        self._name = os.ttyname(self._slave)
        self._fd = open(self._master, 'r+b', buffering=0)
            
        self._thread = threading.Thread(target=self._serial_thread, args=(self._master, self._fd, self._stop))
        self._thread.start()

    
    def port(self):
        return self._name

    # def __del__(self):
    #     self.stop()

    def stop(self):
        self._stop[0] = True
        self._thread.join()

    def _serial_thread(self, master, fd, stop):
        DELAY_PATTERN = b'([\\w\\d*]+),([0-9]+)'
        with Selector() as selector, ExitStack() as stack:
            stack.enter_context(fd)
            selector.register(master, EVENT_READ)


            data : bytes
            data = b''
            while not stop[0]:
                for key, events in selector.select(timeout=0.01):
                    if not events & EVENT_READ:
                        continue
                    
                    data += fd.read()
                    #data += master_files[key.fileobj].read()
                    # if debug:
                    #     print(slave_names[key.fileobj], data, file=sys.stderr)

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
                            fd.write(payload)

class SerialDelayer2:
    def __init__(self) -> None:
        """
        Generate 2 virtual serial ports that forward their data to each other.
        """
        self._stop = [False]

        self._writer_master, self._writer_slave = pty.openpty()
        tty.setraw(self._writer_master)
        os.set_blocking(self._writer_master, False)
        self._writer_name = os.ttyname(self._writer_slave)
        self._writer_fd = open(self._writer_master, 'r+b', buffering=0)

        self._reader_master, self._reader_slave = pty.openpty()
        tty.setraw(self._reader_master)
        os.set_blocking(self._reader_master, False)
        self._reader_name = os.ttyname(self._reader_slave)
        self._reader_fd = open(self._reader_master, 'r+b', buffering=0)
            
        self._thread = threading.Thread(target=self._serial_thread, args=(self._writer_master, self._writer_fd, self._reader_master, self._reader_fd, self._stop), daemon=True)
        self._thread.start()
    

    def reader(self):
        return self._reader_name
    
    def writer(self):
        return self._writer_name

    def __del__(self):
        self.stop()

    def stop(self):
        self._stop[0] = True
        self._thread.join()

    def _serial_thread(self, writer, writer_fd, reader, reader_fd, stop):
        DELAY_PATTERN = b'([a-zA-Z]+),([0-9]+)'
        with Selector() as selector, ExitStack() as stack:
            stack.enter_context(writer_fd)
            selector.register(writer, EVENT_READ)


            data : bytes
            data = b''
            while not stop[0]:
                for key, events in selector.select(timeout=0.1):
                    if not events & EVENT_READ:
                        continue
                    
                    data += writer_fd.read()
                    #data += master_files[key.fileobj].read()
                    # if debug:
                    #     print(slave_names[key.fileobj], data, file=sys.stderr)

                    if len(data) > 0:
                        while b'\n' in data or b';' in data:
                            # There is a fragment
                            if b'\n' in data:
                                pos = data.index(b'\n')
                            if b';' in data:
                                if pos is not None:
                                    pos = min(pos, data.index(b';'))
                                else:
                                    pos = data.index(b';')
                            fragment, data = data[:pos], data[:pos]
                            match = re.match(DELAY_PATTERN, fragment)
                            #sleep(int(match.group(2)) / 1000)
                            reader_fd.write(match.group(1))


# class SerialDelayer:
#     def __init__(self) -> None:
#         """
#         Generate 2 virtual serial ports that forward their data to each other.
#         """
#         num_ports = 2

#         self._stop = [False]

#         self._master_files = {}  # Dict of master fd to master file object.
#         self._slave_names = {}  # Dict of master fd to slave name.
        
#         for _ in range(num_ports):
#             master_fd, slave_fd = pty.openpty()
#             tty.setraw(master_fd)
#             os.set_blocking(master_fd, False)
#             slave_name = os.ttyname(slave_fd)
#             self._master_files[master_fd] = open(master_fd, 'r+b', buffering=0)
#             self._slave_names[master_fd] = slave_name
#         self._thread = threading.Thread(target=self._serial_thread, args=(self._master_files,self._stop))
#         self._thread.start()
    

#     def reader(self):
#         return self._slave_names.values
#     def ports(self) -> list:
#         return list(self._slave_names.values())

#     def stop(self):
#         self._stop[0] = True
#         self._thread.join()

#     def _serial_thread(self, master_files, stop):
#         DELAY_PATTERN = b'([a-zA-Z]+),([0-9]+)'
#         with Selector() as selector, ExitStack() as stack:
#             # Context manage all the master file objects, and add to selector.
#             for fd, f in master_files.items():
#                 stack.enter_context(f)
#                 selector.register(fd, EVENT_READ)

#             data : bytes
#             data = b''
#             while not stop[0]:
#                 for key, events in selector.select(timeout=0.1):
#                     if not events & EVENT_READ:
#                         continue
                    
                    
#                     data += master_files[key.fileobj].read()
#                     # if debug:
#                     #     print(slave_names[key.fileobj], data, file=sys.stderr)

#                     # Write to master files. If loopback is False, don't write
#                     # to the sending file.
#                     for fd, f in master_files.items():
#                         if fd != key.fileobj:#loopback or fd != key.fileobj:
#                             # We assume that only one port will be reading and one port will be writing
#                             # So it is possible to sleep before sending data
#                             if len(data) > 0:
#                                 while b'\n' in data or b';' in data:
#                                     # There is a fragment
#                                     if b'\n' in data:
#                                         pos = data.index(b'\n')
#                                     if b';' in data:
#                                         if pos is not None:
#                                             pos = min(pos, data.index(b';'))
#                                         else:
#                                             pos = data.index(b';')
#                                     fragment, data = data[:pos], data[:pos]
#                                     print(f'Parsing {fragment}')
#                                     match = re.match(DELAY_PATTERN, fragment)
#                                     #sleep(int(match.group(2)) / 1000)
#                                     print(f'Sending back {match.group(1)}')
#                                     f.write(match.group(1))