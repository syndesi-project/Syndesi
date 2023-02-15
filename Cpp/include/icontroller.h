#ifndef ICONTROLLER_H
#define ICONTROLLER_H

#include "sdid.h"
#include "inetwork_bottom.h"

namespace syndesi {

class Frame;
class Network;

namespace SAP {
class IController {
    friend class syndesi::Network;
    friend class syndesi::Frame;

    IController(const IController&) = delete;
    IController(const IController&&) = delete;

   public:
    IController(){};

   private:
    INetwork_bottom* network = nullptr;

   protected:
    /*
     * Called by the user
     */
    // Signal to syndesi that there's some available data on the controller
    void dataAvailable(SyndesiID& deviceID, size_t length) {
        if (network != nullptr) {
            network->controllerDataAvailable(this, deviceID, length);
        }
    }
    /*
     * Implemented by the user
     */
    virtual void init() = 0;
    virtual size_t read(char* buffer, size_t length) = 0;
    // returns the number of bytes written
    virtual size_t write(SyndesiID& deviceID, char* buffer, size_t length) = 0;
    virtual void close() = 0;
};

}
}

#endif