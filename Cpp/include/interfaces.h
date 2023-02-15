/**
 * @file interfaces.h
 *
 * @brief Interfaces between layers.
 *
 * @author Sébastien Deriaz
 * @date 16.08.2022
 */

#ifndef INTERFACES_H
#define INTERFACES_H

//#include "buffer.h"
#include "frame.h"

namespace syndesi {

class Network;
namespace SAP {



class IFrameManager_top {
   public:
    // From top layer
    virtual bool request(Frame& payload) = 0;
};

class IFrameManager_bottom {
   public:
    // From bottom layer
    virtual void indication(Frame& frame) = 0;
    virtual void confirm(Frame& frame) = 0;
};



}  // namespace SAP
}  // namespace syndesi

#endif  // INTERFACES_H
