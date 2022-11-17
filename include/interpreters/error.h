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

    void build(Buffer& dest) {
        dest.allocate(Frame::errorCode_size);
        hton((char*)&errorCode, dest.data(), Frame::errorCode_size);
    }
    void parse(Buffer& src) {
        printf("parsing data ... : \"");
        for(int i = 0;i<src.length();i++) {
            printf("%02X (%u)", src[i], src.length());
            if (i > 10) break;
        }
        printf("\"\n");
        ntoh(src.data(), (char*)&errorCode, Frame::errorCode_size);
    }
    size_t length() { return Frame::errorCode_size; }
};

class ErrorInterpreter : public IInterpreter {
   public:
    struct Callbacks {
        void (*reply)(ErrorPayloadReply& reply) = nullptr;
    };

   private:
    Callbacks callbacks;

   public:
    ErrorInterpreter(Callbacks user_callbacks) { callbacks = user_callbacks; }
    IPayload* parseRequest(Buffer& request) {
        // Should never happen
        return nullptr;
    }
    bool parseReply(Buffer& replyBuffer) {
        ErrorPayloadReply replyPayload;
        replyPayload.parse(replyBuffer);
        if (callbacks.reply != nullptr) {
            callbacks.reply(replyPayload);
        }
        return true;
    }

    IInterpreter::Type type() {return IInterpreter::Type::ERROR;};
};

}  // namespace syndesi

#endif  // ERROR_INTERPRETER_H