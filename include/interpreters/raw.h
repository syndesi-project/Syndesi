/**
 * @file raw.h
 *
 * @brief Raw interpreter
 *
 * @author Sébastien Deriaz
 * @date 16.11.2022
 */

#ifndef RAW_INTERPRETER_H
#define RAW_INTERPRETER_H

#include "../iinterpreter.h"
#include "../ipayload.h"

namespace syndesi {

class RawInterpreter : public IInterpreter {
   public:
    class RawPayloadRequest : public IPayload {
        friend class RawInterpreter;

       public:
        Buffer data;

       private:
        void build(Buffer& dest) { dest = data; }
        void parse(Buffer& src) { data = src; };
        size_t length() { return data.length(); }
    };

    class RawPayloadReply : public IPayload {
        friend class RawInterpreter;

       public:
        Buffer data;

       private:
        void build(Buffer& dest) { dest = data; }
        void parse(Buffer& src) { data = src; };
        size_t length() { return data.length(); }
    };

    struct Callbacks {
        void (*request)(RawPayloadRequest& request,
                        RawPayloadReply* reply) = nullptr;
        void (*reply)(RawPayloadReply& reply) = nullptr;
    };

   private:
    Callbacks callbacks;

   public:
    RawInterpreter(Callbacks user_callbacks) { callbacks = user_callbacks; };

    IPayload* parseRequest(Buffer& requestBuffer) {
        // Parse request
        RawPayloadRequest requestPayload;
        requestPayload.parse(requestBuffer);
        // Prepare reply
        RawPayloadReply* replyPayload = new RawPayloadReply();

        if (callbacks.request != nullptr) {
            callbacks.request(requestPayload, replyPayload);
        }
        return replyPayload;
    }
    bool parseReply(Buffer& replyBuffer) {
        RawPayloadReply replyPayload;
        replyPayload.parse(replyBuffer);
        callbacks.reply(replyPayload);
        return true;
    }

    IInterpreter::Type type() { return IInterpreter::Type::OTHER; };
};

}  // namespace syndesi

#endif  // RAW_INTERPRETER_H