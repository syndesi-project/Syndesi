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
    virtual void build(Buffer& dest) = 0;
    virtual void parse(Buffer& src) = 0;
    virtual size_t length() = 0;
};

}  // namespace syndesi

#endif  // IPAYLOAD_H