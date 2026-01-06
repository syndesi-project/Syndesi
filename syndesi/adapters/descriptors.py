# # File : descriptors.py
# # Author : Sébastien Deriaz
# # License : GPL
# """
# Descriptors are classes that describe how an adapter is connected to its device.
# Depending on the protocol, they can hold strings, integers or enums
# """

# import re
# from abc import abstractmethod
# from dataclasses import dataclass
# from enum import Enum


# descriptors: list[type[Descriptor]] = [
#     SerialPortDescriptor,
#     IPDescriptor,
#     VisaDescriptor,
# ]


# def adapter_descriptor_by_string(string_descriptor: str) -> Descriptor:
#     """
#     Return a corresponding adapter descriptor from a string

#     Parameters
#     ----------
#     string_descriptor : str

#     Returns
#     -------
#     descriptor : Descriptor
#     """
#     for descriptor in descriptors:
#         if re.match(descriptor.DETECTION_PATTERN, string_descriptor):
#             x = descriptor.from_string(string_descriptor)
#             return x
#     raise ValueError(f"Could not parse descriptor string : {string_descriptor}")
