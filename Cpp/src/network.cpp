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
    size_t Nwritten;
    bool output = false;

    if (networkIPController != nullptr) {
        // Determine which controller to use based on address
        switch (frame.id.getAddressType()) {
            case SyndesiID::address_type_t::IPV4:
            case SyndesiID::address_type_t::IPV6:
                frame.getID().setIPPort(settings.getIPPort());

                Nwritten = networkIPController->write(frame.getID(),
                                                      frame.buffer.data(),
                                                      frame.buffer.length());
                if (Nwritten == frame.buffer.length()) {
                    output = true;
                }

                break;
            default:
                printf("Invalid address type\n");
                break;
        }
    }

    // If the send was successful, add the device to the pending list
    if (output) devicesList.Append(frame.getID());

    return output;
};

void Network::response(Frame& frame) {
    if (networkIPController != nullptr) {
        networkIPController->write(frame.getID(), frame.buffer.data(),
                                   frame.buffer.length());
    }
}

/*
 * Lower layer
 */
void Network::controllerDataAvailable(SAP::IController* controller,
                                      SyndesiID& deviceID, size_t length) {
    bool deviceFound = true;
    Frame frame(*controller, deviceID, length);
    devicesList.moveToStart();

    if (devicesList.getLength() > 0) {
        while (devicesList.getCurrent() == deviceID) {
            if (!devicesList.next()) {
                deviceFound = false;
                break;
            }
        }
    } else {
        deviceFound = false;
    }
    
    if (deviceFound) {
        // We were waiting for a response from this device
        devicesList.DeleteCurrent();
        // is reply (we are the host)
        _frameManager->confirm(frame);
    } else {
        // This is a new message (and we're the device)
        // is request (we are the device)
        _frameManager->indication(frame);
    }
}

void Network::init() {
    if (networkIPController != nullptr) {
        networkIPController->network =
            this;                     // Register itself to the controller
        networkIPController->init();  // Initialize the controller
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
