/* THIS FILE IS GENERATED AUTOMATICALLY
*  DO NOT EDIT
*  This file has been written by the script generate_commands.py
*  date : 22-11-03 10:46:23
*
*  Template :
* @file framemanager.h
*
* @brief Management of frames
*
* @author Sébastien Deriaz
* @date 15.08.2022
*/

#ifndef FRAME_MANAGER_H
#define FRAME_MANAGER_H

#include "callbacks.h"
#include "config.h"

using namespace std;

namespace syndesi {

/**
 * @brief Class to manage frames after they've been parsed by the network
 * interface
 *
 */
class FrameManager : SAP::IFrameManager_bottom, SAP::IFrameManager_top {
    friend class Core;

   public:
    FrameManager(){};
    ~FrameManager(){};

   private:
    /*
     * Upper layer
     */
    Callbacks* _callbacks = nullptr;
    void registerCallbacks(Callbacks* callbacks) { _callbacks = callbacks; };
    // From core
    bool request(Frame& frame);
    /*
     * Lower layer
     */
    SAP::INetwork_top* network = nullptr;
    void registerNetwork(SAP::INetwork_top* _network) { network = _network; };
    
    /* Indication (incoming from host)*/
    void indication(Frame& frame) {
        Buffer* requestPayloadBuffer = frame.getPayloadBuffer();
        Payload* reply = nullptr;
        Payload* request = nullptr;

        switch(frame.getCommand()) {
    #if defined(USE_DEVICE_DISCOVER_REQUEST_CALLBACK) && defined(SYNDESI_DEVICE_MODE)
        case commands::DEVICE_DISCOVER:
            request = new DEVICE_DISCOVER_request(requestPayloadBuffer);
            reply = new DEVICE_DISCOVER_reply();
            _callbacks->DEVICE_DISCOVER_request_callback(*(static_cast<DEVICE_DISCOVER_request*>(request)), static_cast<DEVICE_DISCOVER_reply*>(reply));
            break;
#endif
#if defined(USE_REGISTER_READ_16_REQUEST_CALLBACK) && defined(SYNDESI_DEVICE_MODE)
        case commands::REGISTER_READ_16:
            request = new REGISTER_READ_16_request(requestPayloadBuffer);
            reply = new REGISTER_READ_16_reply();
            _callbacks->REGISTER_READ_16_request_callback(*(static_cast<REGISTER_READ_16_request*>(request)), static_cast<REGISTER_READ_16_reply*>(reply));
            break;
#endif
#if defined(USE_REGISTER_WRITE_16_REQUEST_CALLBACK) && defined(SYNDESI_DEVICE_MODE)
        case commands::REGISTER_WRITE_16:
            request = new REGISTER_WRITE_16_request(requestPayloadBuffer);
            reply = new REGISTER_WRITE_16_reply();
            _callbacks->REGISTER_WRITE_16_request_callback(*(static_cast<REGISTER_WRITE_16_request*>(request)), static_cast<REGISTER_WRITE_16_reply*>(reply));
            break;
#endif
#if defined(USE_SPI_READ_WRITE_REQUEST_CALLBACK) && defined(SYNDESI_DEVICE_MODE)
        case commands::SPI_READ_WRITE:
            request = new SPI_READ_WRITE_request(requestPayloadBuffer);
            reply = new SPI_READ_WRITE_reply();
            _callbacks->SPI_READ_WRITE_request_callback(*(static_cast<SPI_READ_WRITE_request*>(request)), static_cast<SPI_READ_WRITE_reply*>(reply));
            break;
#endif
#if defined(USE_SPI_WRITE_ONLY_REQUEST_CALLBACK) && defined(SYNDESI_DEVICE_MODE)
        case commands::SPI_WRITE_ONLY:
            request = new SPI_WRITE_ONLY_request(requestPayloadBuffer);
            reply = new SPI_WRITE_ONLY_reply();
            _callbacks->SPI_WRITE_ONLY_request_callback(*(static_cast<SPI_WRITE_ONLY_request*>(request)), static_cast<SPI_WRITE_ONLY_reply*>(reply));
            break;
#endif
#if defined(USE_I2C_READ_REQUEST_CALLBACK) && defined(SYNDESI_DEVICE_MODE)
        case commands::I2C_READ:
            request = new I2C_READ_request(requestPayloadBuffer);
            reply = new I2C_READ_reply();
            _callbacks->I2C_READ_request_callback(*(static_cast<I2C_READ_request*>(request)), static_cast<I2C_READ_reply*>(reply));
            break;
#endif
#if defined(USE_I2C_WRITE_REQUEST_CALLBACK) && defined(SYNDESI_DEVICE_MODE)
        case commands::I2C_WRITE:
            request = new I2C_WRITE_request(requestPayloadBuffer);
            reply = new I2C_WRITE_reply();
            _callbacks->I2C_WRITE_request_callback(*(static_cast<I2C_WRITE_request*>(request)), static_cast<I2C_WRITE_reply*>(reply));
            break;
#endif

        }

        Frame replyFrame(*reply, frame.getID(), false);
        network->response(replyFrame);
    }

    /* Confirm (incoming from device)*/
    void confirm(Frame& frame) {
        Buffer* replyPayloadBuffer = frame.getPayloadBuffer();
        Payload* reply = nullptr;

        switch(frame.getCommand()) {
    #if defined(USE_ERROR_REPLY_CALLBACK) && defined(SYNDESI_HOST_MODE)
        case commands::ERROR:
            reply = new ERROR_reply(replyPayloadBuffer);
            _callbacks->ERROR_reply_callback(*(static_cast<ERROR_reply*>(reply)));
            break;
#endif
#if defined(USE_DEVICE_DISCOVER_REPLY_CALLBACK) && defined(SYNDESI_HOST_MODE)
        case commands::DEVICE_DISCOVER:
            reply = new DEVICE_DISCOVER_reply(replyPayloadBuffer);
            _callbacks->DEVICE_DISCOVER_reply_callback(*(static_cast<DEVICE_DISCOVER_reply*>(reply)));
            break;
#endif
#if defined(USE_REGISTER_READ_16_REPLY_CALLBACK) && defined(SYNDESI_HOST_MODE)
        case commands::REGISTER_READ_16:
            reply = new REGISTER_READ_16_reply(replyPayloadBuffer);
            _callbacks->REGISTER_READ_16_reply_callback(*(static_cast<REGISTER_READ_16_reply*>(reply)));
            break;
#endif
#if defined(USE_REGISTER_WRITE_16_REPLY_CALLBACK) && defined(SYNDESI_HOST_MODE)
        case commands::REGISTER_WRITE_16:
            reply = new REGISTER_WRITE_16_reply(replyPayloadBuffer);
            _callbacks->REGISTER_WRITE_16_reply_callback(*(static_cast<REGISTER_WRITE_16_reply*>(reply)));
            break;
#endif
#if defined(USE_SPI_READ_WRITE_REPLY_CALLBACK) && defined(SYNDESI_HOST_MODE)
        case commands::SPI_READ_WRITE:
            reply = new SPI_READ_WRITE_reply(replyPayloadBuffer);
            _callbacks->SPI_READ_WRITE_reply_callback(*(static_cast<SPI_READ_WRITE_reply*>(reply)));
            break;
#endif
#if defined(USE_SPI_WRITE_ONLY_REPLY_CALLBACK) && defined(SYNDESI_HOST_MODE)
        case commands::SPI_WRITE_ONLY:
            reply = new SPI_WRITE_ONLY_reply(replyPayloadBuffer);
            _callbacks->SPI_WRITE_ONLY_reply_callback(*(static_cast<SPI_WRITE_ONLY_reply*>(reply)));
            break;
#endif
#if defined(USE_I2C_READ_REPLY_CALLBACK) && defined(SYNDESI_HOST_MODE)
        case commands::I2C_READ:
            reply = new I2C_READ_reply(replyPayloadBuffer);
            _callbacks->I2C_READ_reply_callback(*(static_cast<I2C_READ_reply*>(reply)));
            break;
#endif
#if defined(USE_I2C_WRITE_REPLY_CALLBACK) && defined(SYNDESI_HOST_MODE)
        case commands::I2C_WRITE:
            reply = new I2C_WRITE_reply(replyPayloadBuffer);
            _callbacks->I2C_WRITE_reply_callback(*(static_cast<I2C_WRITE_reply*>(reply)));
            break;
#endif

        }
    }

};

}  // namespace syndesi

#endif  // FRAME_MANAGER_H
