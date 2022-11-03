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

#include "payloads.h"
#include "sdid.h"

namespace syndesi {

class Frame {
    friend class Network;
    friend class FrameManager;

    union NetworkHeader {
        struct {
            // Frame must be re-routed to another device,
            // this means it contains a sdid after the
            // network header
            bool routing : 1;
            // Signals that another frame is following the current one
            bool follow : 1;
            bool request_nReply : 1;  // Request (1) or reply (0)
            unsigned char reserved : 5;
        } fields;
        uint8_t value;
    };

    static const size_t command_size = sizeof(cmd_t);
    static const size_t addressingHeader_size = 1;

   public:
    typedef uint16_t frameLength_t;
    static const size_t networkHeader_size = sizeof(NetworkHeader);
    static const size_t frameLength_size = sizeof(frameLength_t);

   public:
    /**
     * @brief Construct a frame object from a payload and SyndesiID
     *
     * @param payload payload
     * @param id id of device
     */
    Frame(Payload& payload, SyndesiID& id, bool isRequest);

    /**
     * @brief Construct a frame from a buffer object
     *
     */
    Frame(Buffer& buffer, SyndesiID& id);

    /**
     * @brief Destroy the Frame object
     *
     */
    ~Frame() {}

   private:
    cmd_t command;
    NetworkHeader networkHeader;
    frameLength_t frameLength;
    Buffer* _buffer = nullptr;
    SyndesiID* _id = nullptr;

    // Predefine the payloadBuffer (when creating the frame from the lower
    // layer)
    Buffer* _payloadBuffer = nullptr;

   public:
    /**
     * @brief Get the command ID
     *
     * @return cmd_t
     */
    cmd_t getCommand();

    /**
     * @brief Get the payload buffer
     *
     * @return pointer to buffer
     */
    Buffer* getPayloadBuffer();

    /**
     * @brief Get the SyndesiID
     *
     */
    SyndesiID& getID() { return *_id; };
};

}  // namespace syndesi

#endif  // FRAME_H