/**
 * @file error.h
 *
 * @brief Error interpreter, used by all syndesi implementations
 *
 * @author Sébastien Deriaz
 * @date 16.11.2022
 */

#ifndef ERROR_INTERPRETER_H
#define ERROR_INTERPRETER_H

#include "../frame.h"
#include "../iinterpreter.h"
#include "../ipayload.h"
#include "../syndesi_tools.h"

namespace syndesi {

class ErrorPayloadReply : public IPayload {
   public:
    Frame::ErrorCode errorCode = Frame::ErrorCode::NO_ERROR;

    void build(char* buffer) {
        hton((char*)&errorCode, buffer, Frame::errorCode_size);
    }
    void parse(char* buffer, size_t length) {
        if (length >= Frame::errorCode_size) {
            ntoh(buffer, (char*)&errorCode, Frame::errorCode_size);
        }
    }
    size_t length() { return Frame::errorCode_size; }
};

class ErrorInterpreter : public IInterpreter {
    void (*reply)(ErrorPayloadReply& reply);

   public:
    ErrorInterpreter(void (*reply)(ErrorPayloadReply& reply) = nullptr) {
        this->reply = reply;
    };
    IPayload* parseRequest(char* buffer, size_t length) {
        // Should never happen
        (void)buffer;
        (void)length;
        return nullptr;
    }
    bool parseReply(char* buffer, size_t length) {
        ErrorPayloadReply replyPayload;
        replyPayload.parse(buffer, length);
        if (reply != nullptr) {
            reply(replyPayload);
        }
        return true;
    }

    IInterpreter::Type type() { return IInterpreter::Type::ERROR; };
};

}  // namespace syndesi

#endif  // ERROR_INTERPRETER_H