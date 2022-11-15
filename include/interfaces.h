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

#include "buffer.h"
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

class INetwork_top {
   public:
    // From top layer
    virtual bool request(Frame& frame) = 0;
    virtual void response(Frame& frame) = 0;
};

class IController;

class INetwork_bottom {
    public:
    virtual void controllerDataAvailable(IController* controller,
                                         SyndesiID& deviceID,
                                         size_t length) = 0;
};



class IController {
    friend class syndesi::Network;

    IController(const IController&) = delete;
    IController(const IController&&) = delete;

   public:
    IController(){};

   private:
    INetwork_bottom* network = nullptr;

   public:
    /*
     * Callable by the user
     */
   public:
    // void dataAvailable() { network->controllerDataAvailable(this);}

   protected:
    // unsigned short IPPort() { return network->port(); };
    // void setCustomIPPort(unsigned short port) { network->setCustomPort(port);
    // };

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
    // virtual SyndesiID& getSyndesiID() = 0;
    virtual size_t read(char* buffer, size_t length) = 0;
    // returns the number of bytes written
    virtual size_t write(SyndesiID& deviceID, char* buffer, size_t length) = 0;
    virtual void close() = 0;
};

}  // namespace SAP
}  // namespace syndesi

#endif  // INTERFACES_H
