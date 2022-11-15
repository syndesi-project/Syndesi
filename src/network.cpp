/**
 * @file network.cpp
 *
 * @brief Interfacing with the communication protocols (IP, UART, RS 485, ...)
 *
 * @author Sébastien Deriaz
 * @date 15.08.2022
 */

#include "network.h"

#include <iostream>

namespace syndesi {

SAP::IController* networkIPController = nullptr;
SAP::IController* networkUARTController = nullptr;
SAP::IController* networkRS485Controller = nullptr;

unsigned short Network::port() { return settings.getIPPort(); }

/*
 * From upper layer
 */
bool Network::request(Frame& frame) {
    Frame::NetworkHeader networkHeader;
    networkHeader.fields.routing = frame.getID().reroutes() > 0 ? true : false;
    networkHeader.fields.request_nReply = true;
    networkHeader.fields.reserved = 0;
    size_t Nwritten;
    bool output = false;

    if (networkIPController != nullptr) {
        // Determine which controller to use based on address
        switch (frame._id->getAddressType()) {
            case SyndesiID::address_type_t::IPV4:
            case SyndesiID::address_type_t::IPV6:
                frame.getID().setIPPort(settings.getIPPort());

                Nwritten =
                    networkIPController->write(frame.getID(), frame._buffer->data(),
                                        frame._buffer->length());
                if (Nwritten == frame._buffer->length()) {
                    output = true;
                }
                // The controllerDataAvailable method will take care of the
                // confirm
                break;
            default:
                printf("Invalid address type\n");
                break;
        }
    }
    return output;
};

void Network::response(Frame& frame) {
    if (networkIPController != nullptr) {
        networkIPController->write(frame.getID(), frame._buffer->data(),
                            frame._buffer->length());
    }
}

/*
 * Lower layer
 */

Frame Network::readFrame(SyndesiID& id, SAP::IController* controller) {
    // Start by reading the first few bytes of the frame to know the length,
    // then read the rest of it. If multiple frames are present in the buffer,
    // they will be treated separately
    const size_t header_size =
        Frame::networkHeader_size + Frame::frameLength_size;
    char header[header_size];
    // Read the header
    controller->read(header, header_size);
    // Extract the frame length (without the header)
    Frame::frameLength_t frameLength;
    ntoh(header + Frame::networkHeader_size, (char*)&frameLength,
         Frame::frameLength_size);

    // Calculate the total frame length (with header)
    size_t totalFrameLength = frameLength + header_size;
    Buffer buffer(totalFrameLength);
    // copy the header into the newly created buffer
    memcpy(buffer.data(), header, header_size);

    // Read the rest of the data from the network (with offset due to the header
    // written at the beginning of the buffer)
    controller->read(buffer.data() + header_size,
                     buffer.length() - header_size);
    return Frame(buffer, id);
}

void Network::controllerDataAvailable(SAP::IController* controller,
                                      SyndesiID& deviceID, size_t length) {
    Frame frame = readFrame(deviceID, controller);

    if (frame.networkHeader.fields.request_nReply) {
        // is request (we are the device)
        _frameManager->indication(frame);
    } else {
        // is reply (we are the host)
        _frameManager->confirm(frame);
    }
}

void Network::init() {
    if (networkIPController != nullptr) {
        networkIPController->network = this;  // Register itself to the controller
        networkIPController->init(); // Initialize the controller
    }
    if (networkRS485Controller != nullptr) {
        networkIPController->network = this;
        networkIPController->init();
    }
    if (networkUARTController != nullptr) {
        networkUARTController->network = this;
        networkUARTController->init();
    }
}

}  // namespace syndesi
