#include "frame.h"

namespace syndesi {

Frame::Frame(Payload& payload, SyndesiID& id, bool isRequest) {
    // Set the values
    _id = &id;
    command = payload.getCommand();

    // TODO update
    networkHeader.value = 0;
    networkHeader.fields.follow = false;
    networkHeader.fields.request_nReply = isRequest;
    networkHeader.fields.routing = _id->reroutes() > 0 ? true : false;

    // Calculate the length of the frame
    size_t addressing_size = _id->getTotalAdressingSize();
    frameLength = addressing_size + command_size + payload.payloadLength();
    size_t packetLength = networkHeader_size + frameLength_size + frameLength;
    size_t pos = 0;

    // Create a buffer
    _buffer = new Buffer(packetLength);

    // Write networkHeader
    pos += hton(reinterpret_cast<char*>(&networkHeader), _buffer->data(),
                networkHeader_size);
    // Write frame length
    pos += hton(reinterpret_cast<char*>(&frameLength), _buffer->data() + pos,
                frameLength_size);
    // Write ID(s) (start at addressingHeader_size)
    Buffer IDBuffer(_buffer, pos, addressing_size);
    _id->buildAddressingBuffer(&IDBuffer);
    pos += addressing_size;

    // Write cmd_t
    pos += hton(reinterpret_cast<char*>(&command), _buffer->data() + pos,
                command_size);
    // Write payload
    Buffer payloadBuffer(_buffer, pos);
    payload.build(&payloadBuffer);
}

Frame::Frame(Buffer& buffer, SyndesiID& id) {
    size_t pos = 0;
    _buffer = &buffer;
    _id = &id;
    // Read network header
    pos += ntoh(_buffer->data() + pos, reinterpret_cast<char*>(&networkHeader),
                networkHeader_size);
    // Read the frame length (no including the network header size and
    // itself)
    pos += ntoh(_buffer->data() + pos, reinterpret_cast<char*>(&frameLength),
                frameLength_size);

    // Check if the frame contains a SyndesiID (to identify a sub-device)
    if (networkHeader.fields.routing) {
        // Create a buffer for SyndesiID to read
        Buffer addressingBuffer = Buffer(_buffer, pos);
        _id->parseAddressingBuffer(&addressingBuffer);
        pos += _id->getTotalAdressingSize();
    }
    // Read command
    pos += ntoh(_buffer->data() + pos, reinterpret_cast<char*>(&command),
                command_size);
    // Read payload length
    _payloadBuffer = new Buffer(_buffer, pos);
}

cmd_t Frame::getCommand() { return command; }

Buffer* Frame::getPayloadBuffer() { return _payloadBuffer; }

}  // namespace syndesi