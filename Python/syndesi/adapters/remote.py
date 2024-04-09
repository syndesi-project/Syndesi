# remote.py
# Sébastien Deriaz
# 09.04.2024
#
# The remote adapter allows for commands to be issued on a different device through TCP
# The goal is to istanciate a class as such :
#
# Only adapter :
#   # The remote computer is accessed with 192.168.1.1
#   # The device (connected to the remote computer) is accessed with 192.168.2.1
#   my_adapter = Remote('192.168.1.1', IP('192.168.2.1'))
#
# Protocol :
#   my_protocol = SCPI(Remote('192.168.1.1', Serial('/dev/ttyUSB0')))
#
#
# Driver :
#   my_device = Driver(Remote('192.168.1.1', VISA('...')))