/**
 * @file framemanager.cpp
 *
 * @brief Management of frames
 *
 * @author Sébastien Deriaz
 * @date 15.08.2022
 */

#include "framemanager.h"

namespace syndesi {
/*
 * Upper layer
 */
bool FrameManager::request(Frame& frame) {
    if (network != nullptr) {
        return network->request(frame);
    }
    return false;
}

void FrameManager::indication(Frame& frame) {
    Frame* reply = nullptr;
    Buffer* replyBuffer;
    Buffer& payloadBuffer = frame.getPayloadBuffer();

    if (frame.networkHeader.fields.error) {
        // We shouldn't get an error request
        reply = new Frame(frame.getID(), Frame::ErrorCode::INVALID_PAYLOAD);
    } else {
        // No need to look for an error interpreter here, a device should
        // never receive an error request

        for (IInterpreter** interpreter = &first_interpreter;
             *interpreter != nullptr; *interpreter = (*interpreter)->next) {
            if ((*interpreter)->type() == IInterpreter::Type::ERROR) {
                // An error interpreter is useless here
            } else {
                IPayload* payload = (*interpreter)->parseRequest(payloadBuffer);
                if(payload) {
                    reply = new Frame(frame.getID(), *payload);
                    delete payload;
                    break;
                }
            }
        }

        if(reply == nullptr) {
            // If no frame was made, create one
            reply = new Frame(frame.getID(), Frame::ErrorCode::NO_INTERPETER);
        }
    }
    if (reply != nullptr) {
        network->response(*reply);
    }

    delete reply;
}

void FrameManager::confirm(Frame& frame) {
    Buffer* replyBuffer;
    Buffer& payloadBuffer = frame.getPayloadBuffer();

    printf("confirm...\n");
    for (IInterpreter** interpreter = &first_interpreter;
         *interpreter != nullptr; *interpreter = (*interpreter)->next) {
        
        if ((*interpreter)->type() == IInterpreter::Type::ERROR) {
            if (frame.networkHeader.fields.error) {
                // We found an error interpreter, it will be able to
                // parse the reply
                (*interpreter)->parseReply(payloadBuffer);
            }
        } else if ((*interpreter)->parseReply(payloadBuffer)) {
            // We found one that accepts this payload
            break;
        }
    }
    // If no interpreter was found... then too bad
}

}  // namespace syndesi