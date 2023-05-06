# Syndesi C++ library

## Notes 29.04.2023

Add a "Serial finder" protocol that is able to find a serial port even if it has changed name (it basically exludes all of the others specified in a blacklist and looks for the remaining one)

## Notes 15.08.2022

The payload manager is probably not going to be used, each class below includes the class above.


## Notes 16.08.2022

Buffer problem : when we get a frame from the IP stack, we know its size and we can allocate accordingly

When we create the reply, we do not know any clean way to create the right buffer size when building the payload (and then adding the size, the command, the sdid etc...)

The solution is to ask the Buffer to tell us what's the offset of the subbuffer, then we can create a new buffer with the payload size + the offset (since the reply frame will have exactly the same header length, including sdid(s))
