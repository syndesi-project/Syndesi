# Sébastien Deriaz
# 21.02.2023
# 
# VISA descriptor
# NOTE : Not sure this is the right approach, check this later

from .descriptor import Descriptor

import pyvisa

rm = pyvisa.ResourceManager()

class VISA(Descriptor):
    def __init__(self, descriptor : str) -> None:
        super().__init__()

        descriptors = rm.list_resources()

        if descriptor not in descriptors:
            raise RuntimeError(f'Descriptor "{descriptor} unavailable". Availables are : {descriptors}')

        self._inst = rm.open_resource(descriptor)

    def read(self):
        return self._inst.read()

    def write(self, data):
        self._inst.write(data)

    def __del__(self):
        self._inst.close()