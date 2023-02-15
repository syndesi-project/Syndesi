#include "frame.h"

namespace syndesi {

Frame::Frame(SyndesiID& id, ErrorCode errorCode) : id(id) {
    // Create a new frame from an error code
    // Copy the error code in the buffer
    buffer.allocate(networkHeader_size + errorCode_size);
    hton((char*)&errorCode, buffer.data() + networkHeader_size, errorCode_size);

    networkHeader.value = 0;
    networkHeader.fields.follow = false;
    networkHeader.fields.routing = id.reroutes() > 0 ? true : false;
    networkHeader.fields.error = true;

    // Write network header
    buffer.data()[0] = networkHeader.value;
}

Frame::Frame(SyndesiID& id, IPayload& payload) : id(id) {
    size_t pos = 0;
    // Create a new frame from a payload
    buffer.allocate(payload.length() + header_size +
                    id.getTotalAdressingSize());
    // TODO update
    networkHeader.value = 0;
    networkHeader.fields.follow = false;
    networkHeader.fields.routing = id.reroutes() > 0 ? true : false;
    networkHeader.fields.error = false;

    size_t addressing_size = id.getTotalAdressingSize();
    payloadLength = addressing_size + payload.length();

    // Write networkHeader
    pos += hton(reinterpret_cast<char*>(&networkHeader), buffer.data(),
                networkHeader_size);
    // Write frame length
    pos += hton(reinterpret_cast<char*>(&payloadLength), buffer.data() + pos,
                payloadLength_size);
    
    // Write ID(s) (start at addressingHeader_size)
    // id.buildAddressingBuffer(buffer.data() + pos + addressing_size,
    // buffer.length() - pos - addressing_size);

    // pos += addressing_size;

    // Write payload

    payload.build(buffer.data() + pos);
}

Frame::Frame(SAP::IController& controller, SyndesiID& id, size_t availableLength) : id(id) {
    // Create a frame from the read data of the controller
    (void)availableLength;
    // TODO : Use the length to either
    // - build the frame piece by piece
    // - ignore the data and create the frame once there's enough data
    
    // Read the header (or the network header + error code)
    char headerBuffer[header_size];
    controller.read(headerBuffer, header_size);

    // Write the network header
    networkHeader.value = headerBuffer[0];

    if (networkHeader.fields.routing) {
        // Create a buffer for SyndesiID to read
        /*Buffer addressingBuffer = Buffer(_buffer, pos);
        _id->parseAddressingBuffer(&addressingBuffer);
        pos += _id->getTotalAdressingSize();*/
        // TODO : Add this
    }

    if (networkHeader.fields.error) {
        // No need to read the payload
        // buffer = new Buffer(header_size);
        buffer.fromBuffer(headerBuffer, header_size);
        // Copy into the buffer
    } else {
        // Get the length and read the payload
        ntoh(headerBuffer + networkHeader_size, (char*)&payloadLength,
             payloadLength_size);
        buffer.allocate(header_size + payloadLength);
        if (buffer.data()) {
            // Copy the header back in the buffer
            memcpy(buffer.data(), headerBuffer, header_size);
            // Read the payload
            controller.read(buffer.data() + header_size, payloadLength);
        }
    }
}

char* Frame::getPayloadBuffer() {
    // Return a smaller buffer, for the payload only
    if (networkHeader.fields.error) {
        // Remove only the network header
        return buffer.data() + networkHeader_size;
    } else {
        // Remove the whole header (network header + length)
        return buffer.data() + header_size;
    }
}

size_t Frame::getPayloadLength() { return payloadLength; }

}  // namespace syndesi