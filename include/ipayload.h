/**
 * @file ipayload.h
 *
 * @brief Payload interface
 *
 * @ingroup syndesi
 *
 * @author Sébastien Deriaz
 * @date 16.11.2022
 */

#ifndef IPAYLOAD_H
#define IPAYLOAD_H

#include "buffer.h"

namespace syndesi {

class IPayload {
    friend class FrameManager;
    friend class IInterpreter;

   public:
    virtual ~IPayload() {};
    virtual size_t length() = 0;
    virtual void build(char* buffer) = 0;
    virtual void parse(char* buffer, size_t length) = 0;
};

}  // namespace syndesi

#endif  // IPAYLOAD_H