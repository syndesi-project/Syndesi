

#ifndef INETWORK_BOTTOM_H
#define INETWORK_BOTTOM_H

#include "frame.h"
#include "sdid.h"

namespace syndesi {

namespace SAP {

class IController;

class INetwork_bottom {
    public:
    virtual void controllerDataAvailable(IController* controller,
                                         SyndesiID& deviceID,
                                         size_t length) = 0;
};

}
}

#endif // INETWORK_BOTTOM_H