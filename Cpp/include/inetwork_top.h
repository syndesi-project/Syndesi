

#ifndef INETWORK_TOP_H
#define INETWORK_TOP_H

#include "frame.h"
#include "sdid.h"

namespace syndesi {

namespace SAP {

class INetwork_top {
   public:
    // From top layer
    virtual bool request(syndesi::Frame& frame) = 0;
    virtual void response(syndesi::Frame& frame) = 0;
};

}
}

#endif // INETWORK_TOP_H