# File : adapter_manager.py
# Author : Sébastien Deriaz
# License : GPL
#
# The adapter manager instanciates adapters based on a given descriptor
# It is used by the backend to create adapters

# from .adapter_backend import AdapterBackend
# from .descriptors import Descriptor, IPDescriptor, SerialPortDescriptor, VisaDescriptor
# from .ip_backend import IPBackend
# from .serialport_backend import SerialPortBackend
# from .visa_backend import VisaBackend


# class AdapterManager:
#     def __init__(self) -> None:
#         self.adapters : Dict[str, AdapterBackend] = {}

#     def get_adapter(self, descriptor: Descriptor) -> AdapterBackend:
#         string_descriptor = str(descriptor)
#         if string_descriptor not in self.adapters:
#             # The adapter doesn't exist, create it
#             if isinstance(
#                 descriptor, SerialPortDescriptor
#             ):  # Add mandatory timeout and stop_condition here ?
#                 self.adapters[string_descriptor] = SerialPortBackend(
#                     descriptor=SerialPortDescriptor(
#                         port=descriptor.port, baudrate=descriptor.baudrate
#                     )
#                 )
#             elif isinstance(descriptor, IPDescriptor):
#                 self.adapters[string_descriptor] = IPBackend(descriptor=descriptor)
#             elif isinstance(descriptor, VisaDescriptor):
#                 self.adapters[string_descriptor] = VisaBackend(descriptor=descriptor)
#             else:
#                 raise ValueError(f"Unsupported descriptor : {descriptor}")

#         return self.adapters[string_descriptor]

#     def close_adapter(self, descriptor: Descriptor):
#         string_decriptor = str(descriptor)
#         if string_decriptor in self.adapters:
#             adapter = self.adapters.pop(string_decriptor)
#             adapter.close()


# # The singleton instance
# adapterManager = AdapterManager()
