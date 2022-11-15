/* THIS FILE IS GENERATED AUTOMATICALLY
 *  DO NOT EDIT
 *  This file has been written by the script generate_commands.py
 *  date : 22-11-15 10:03:28
 */

#ifndef CALLBACKS_H
#define CALLBACKS_H


#ifndef ARDUINO
#include "config.h" // Added because the defines weren't propagated
#endif
#include "payloads.h"
#include "interfaces.h"

namespace syndesi {

class Callbacks {
    friend class Core;
    private:
        SAP::IFrameManager_top* _frameManager = nullptr;
        void registerFrameManager(SAP::IFrameManager_top* frameManager) {_frameManager = frameManager;};
        Callbacks() {};
    public:
        void indication(Frame& payload);
        void confirm(Frame& payload);

#if defined(USE_ERROR_REPLY_CALLBACK) && defined(SYNDESI_HOST_MODE)
    void (*ERROR_reply_callback)(ERROR_reply&);
#endif
#if defined(USE_DEVICE_DISCOVER_REQUEST_CALLBACK) && defined(SYNDESI_DEVICE_MODE)
    void (*DEVICE_DISCOVER_request_callback)(DEVICE_DISCOVER_request&, DEVICE_DISCOVER_reply*);
#endif
#if defined(USE_DEVICE_DISCOVER_REPLY_CALLBACK) && defined(SYNDESI_HOST_MODE)
    void (*DEVICE_DISCOVER_reply_callback)(DEVICE_DISCOVER_reply&);
#endif
#if defined(USE_REGISTER_READ_16_REQUEST_CALLBACK) && defined(SYNDESI_DEVICE_MODE)
    void (*REGISTER_READ_16_request_callback)(REGISTER_READ_16_request&, REGISTER_READ_16_reply*);
#endif
#if defined(USE_REGISTER_READ_16_REPLY_CALLBACK) && defined(SYNDESI_HOST_MODE)
    void (*REGISTER_READ_16_reply_callback)(REGISTER_READ_16_reply&);
#endif
#if defined(USE_REGISTER_WRITE_16_REQUEST_CALLBACK) && defined(SYNDESI_DEVICE_MODE)
    void (*REGISTER_WRITE_16_request_callback)(REGISTER_WRITE_16_request&, REGISTER_WRITE_16_reply*);
#endif
#if defined(USE_REGISTER_WRITE_16_REPLY_CALLBACK) && defined(SYNDESI_HOST_MODE)
    void (*REGISTER_WRITE_16_reply_callback)(REGISTER_WRITE_16_reply&);
#endif
#if defined(USE_SPI_READ_WRITE_REQUEST_CALLBACK) && defined(SYNDESI_DEVICE_MODE)
    void (*SPI_READ_WRITE_request_callback)(SPI_READ_WRITE_request&, SPI_READ_WRITE_reply*);
#endif
#if defined(USE_SPI_READ_WRITE_REPLY_CALLBACK) && defined(SYNDESI_HOST_MODE)
    void (*SPI_READ_WRITE_reply_callback)(SPI_READ_WRITE_reply&);
#endif
#if defined(USE_SPI_WRITE_ONLY_REQUEST_CALLBACK) && defined(SYNDESI_DEVICE_MODE)
    void (*SPI_WRITE_ONLY_request_callback)(SPI_WRITE_ONLY_request&, SPI_WRITE_ONLY_reply*);
#endif
#if defined(USE_SPI_WRITE_ONLY_REPLY_CALLBACK) && defined(SYNDESI_HOST_MODE)
    void (*SPI_WRITE_ONLY_reply_callback)(SPI_WRITE_ONLY_reply&);
#endif
#if defined(USE_I2C_READ_REQUEST_CALLBACK) && defined(SYNDESI_DEVICE_MODE)
    void (*I2C_READ_request_callback)(I2C_READ_request&, I2C_READ_reply*);
#endif
#if defined(USE_I2C_READ_REPLY_CALLBACK) && defined(SYNDESI_HOST_MODE)
    void (*I2C_READ_reply_callback)(I2C_READ_reply&);
#endif
#if defined(USE_I2C_WRITE_REQUEST_CALLBACK) && defined(SYNDESI_DEVICE_MODE)
    void (*I2C_WRITE_request_callback)(I2C_WRITE_request&, I2C_WRITE_reply*);
#endif
#if defined(USE_I2C_WRITE_REPLY_CALLBACK) && defined(SYNDESI_HOST_MODE)
    void (*I2C_WRITE_reply_callback)(I2C_WRITE_reply&);
#endif


};

//extern Callbacks callbacks;

}

#endif // CALLBACKS_H