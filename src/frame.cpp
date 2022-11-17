#include "frame.h"

namespace syndesi {

Frame::Frame(SyndesiID& id, ErrorCode errorCode) : id(id) {
    // Create a new frame from an error code
    // Copy the error code in the buffer
    buffer = new Buffer(networkHeader_size + errorCode_size);
    hton((char*)&errorCode, buffer->data() + networkHeader_size,
         errorCode_size);

    networkHeader.value = 0;
    networkHeader.fields.follow = false;
    networkHeader.fields.routing = id.reroutes() > 0 ? true : false;
    networkHeader.fields.error = true;

    // Write network header
    buffer->data()[0] = networkHeader.value;
}

Frame::Frame(SyndesiID& id, IPayload& payload) : id(id) {
    size_t pos = 0;
    // Create a new frame from a payload
    buffer =
        new Buffer(payload.length() + header_size + id.getTotalAdressingSize());
    // TODO update
    networkHeader.value = 0;
    networkHeader.fields.follow = false;
    networkHeader.fields.routing = id.reroutes() > 0 ? true : false;
    networkHeader.fields.error = false;

    size_t addressing_size = id.getTotalAdressingSize();
    size_t payloadLength = addressing_size + payload.length();

    // Write networkHeader
    pos += hton(reinterpret_cast<char*>(&networkHeader), buffer->data(),
                networkHeader_size);
    // Write frame length
    pos += hton(reinterpret_cast<char*>(&payloadLength), buffer->data() + pos,
                payloadLength_size);
    // Write ID(s) (start at addressingHeader_size)
    Buffer IDBuffer(buffer, pos, addressing_size);
    id.buildAddressingBuffer(&IDBuffer);
    pos += addressing_size;

    // Write payload
    Buffer payloadBuffer(buffer, pos);
    payload.build(payloadBuffer);
    printf("payload buffer : ");
    payloadBuffer.print();
    printf("\nBuffer : ");
    buffer->print();
    printf("\n");

}

Frame::Frame(SAP::IController& controller, SyndesiID& id) : id(id) {
    // Create a frame from the read data of the controller
    payloadLength_t payloadLength;

    // Read the header (or the network header + error code)
    char headerBuffer[header_size];
    controller.read(headerBuffer, header_size);

    // Write the network header
    ntoh(headerBuffer, (char*)&networkHeader, networkHeader_size);

    

    if (networkHeader.fields.routing) {
        // Create a buffer for SyndesiID to read
        /*Buffer addressingBuffer = Buffer(_buffer, pos);
        _id->parseAddressingBuffer(&addressingBuffer);
        pos += _id->getTotalAdressingSize();*/
        // TODO : Add this
    }

    if (networkHeader.fields.error) {
        // No need to read the payload
        buffer = new Buffer(header_size);
        buffer->fromBuffer(headerBuffer, header_size, true, false);
        // Copy into the buffer
    } else {
        // Get the length and read the payload
        ntoh(headerBuffer, (char*)&payloadLength, payloadLength_size);
        buffer = new Buffer(header_size + payloadLength);
        // Read the payload
        controller.read(buffer->data() + header_size, payloadLength);
    }

    /*printf("Frame (%u): ", buffer->length());
    buffer->print();
    printf("\n");*/
}

Buffer& Frame::getPayloadBuffer() {
    if (buffer != nullptr) {
        // Return a smaller buffer, for the payload only
        if (networkHeader.fields.error) {
            // Remove only the network header
            payloadBuffer = buffer->offset(networkHeader_size);
        } else {
            // Remove the whole header (network header + length)
            payloadBuffer = buffer->offset(header_size);
        }
    }

    return payloadBuffer;
}

}  // namespace syndesi