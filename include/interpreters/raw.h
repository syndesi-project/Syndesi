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
        void build(char* buffer) { data.dump(buffer, length()); }
        void parse(char* buffer, size_t length) {
            data.fromBuffer(buffer, length);
        };
        size_t length() { return data.length(); }
    };

    class RawPayloadReply : public IPayload {
        friend class RawInterpreter;

       public:
        Buffer data;

       private:
        void build(char* buffer) { data.dump(buffer, length()); };
        void parse(char* buffer, size_t length) {
            data.fromBuffer(buffer, length);
        };
        size_t length() { return data.length(); }
    };

    void (*request)(RawPayloadRequest& request, RawPayloadReply* reply);
    void (*reply)(RawPayloadReply& reply);

   public:
    //RawInterpreter() = delete;
    RawInterpreter(const syndesi::RawInterpreter&) = delete;
    RawInterpreter(const syndesi::RawInterpreter&&) = delete;

    RawInterpreter(void (*request)(RawPayloadRequest&,
                                   RawPayloadReply*) = nullptr,
                   void (*reply)(RawPayloadReply&) = nullptr) {
        this->request = request;
        this->reply = reply;
    }

    IPayload* parseRequest(char* buffer, size_t length) {
        // Parse request
        RawPayloadRequest requestPayload;
        requestPayload.parse(buffer, length);
        // Prepare reply
        RawPayloadReply* replyPayload = new RawPayloadReply();

        if (request != nullptr) {
            request(requestPayload, replyPayload);
        }
        return replyPayload;
    }
    bool parseReply(char* buffer, size_t length) {
        RawPayloadReply replyPayload;
        replyPayload.parse(buffer, length);
        reply(replyPayload);
        return true;
    }

    IInterpreter::Type type() { return IInterpreter::Type::TEST; };
};

}  // namespace syndesi

#endif  // RAW_INTERPRETER_H