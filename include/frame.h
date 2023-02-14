/**
 * @file frame.h
 *
 * @brief Frame library
 *
 * @ingroup syndesi
 *
 * @author Sébastien Deriaz
 * @date 27.06.2022
 */

#ifndef FRAME_H
#define FRAME_H

using namespace std;

#include "sdid.h"
#include "ipayload.h"
#include "icontroller.h"

#ifdef ARDUINO
#include <Arduino.h>
#define SLEEP(x) delay(x)
#else
#include <unistd.h>
#define SLEEP(x) usleep((x)*1000)
#endif

namespace syndesi {

class Frame {
    friend class Network;
    friend class FrameManager;

   public:
    enum ErrorCode : unsigned short {
        NO_ERROR = 0,
        NO_INTERPETER = 1,
        INVALID_PAYLOAD = 2};

    static const size_t errorCode_size = 2;

    union NetworkHeader {
        struct {
            // Frame must be re-routed to another device,
            // this means it contains a sdid after the
            // network header
            bool routing : 1;
            // Signals that another frame is following the current one
            bool follow : 1;
            bool error : 1;  // Error frame
            unsigned char reserved : 5;
        } fields;
        uint8_t value;
    };
    static const size_t networkHeader_size = sizeof(NetworkHeader);

    

    static const size_t addressingHeader_size = 1;

    typedef uint16_t payloadLength_t;

    static const size_t payloadLength_size = sizeof(payloadLength_t);

    // NOTE : the error code is the same size as the payload length
    // That's on purpose so that <header_size> bytes can be read every time, and
    // depending on the value of the network header, the rest is interpreted as
    // either payload length or error code value
    static const size_t header_size = networkHeader_size + payloadLength_size;

   public:
    // Create a frame locally 
    Frame(SyndesiID& id, ErrorCode errorCode);
    Frame(SyndesiID& id, IPayload& payload);
    // Create a frame from received data
    Frame(SAP::IController& controller, SyndesiID& id, size_t availableLength);

    

    ~Frame() {}

   private:
    NetworkHeader networkHeader;
    Buffer buffer;
    payloadLength_t payloadLength = 0;
    SyndesiID& id;

   public:
    /**
     * @brief Get the payload buffer
     *
     * @return pointer to buffer
     */
    Buffer* getBuffer();

    char* getPayloadBuffer();
    size_t getPayloadLength();

    /**
     * @brief Get the SyndesiID
     *
     */
    SyndesiID& getID() { return id; };
};

}  // namespace syndesi

#endif  // FRAME_H