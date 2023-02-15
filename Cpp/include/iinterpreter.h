/**
 * @file iinterpreter.h
 *
 * @brief Interpreter interface
 *
 * @author Sébastien Deriaz
 * @date 16.11.2022
 */

#ifndef IINTERPRETER_H
#define IINTERPRETER_H

#include "buffer.h"
#include "ipayload.h"

namespace syndesi {
class IInterpreter {
    friend class FrameManager;

   protected:
    IInterpreter* next = nullptr;
    virtual IPayload* parseRequest(char* buffer, size_t length) = 0;
    virtual bool parseReply(char* buffer, size_t length) = 0;
    enum Type : unsigned char { ERROR, BCS, OTHER, TEST=9};
    virtual Type type() = 0;
};

}  // namespace syndesi

#endif