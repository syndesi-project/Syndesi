/**
 * @file network.h
 *
 * @brief Interfacing with the communication protocols (IP, UART, RS 485, ...)
 *
 * @author Sébastien Deriaz
 * @date 15.08.2022
 */

#ifndef NETWORK_INTERFACE_H
#define NETWORK_INTERFACE_H

#include <stdint.h>

#include "frame.h"
#include "framemanager.h"
#include "interfaces.h"
#include "sdid.h"
#include "settings.h"

using namespace std;

namespace syndesi {
class Network : SAP::INetwork_top, public SAP::INetwork_bottom {
    /**
     * @brief Network frame instance
     * @note contains a network header and a payload. The payload is forwarded
     * to the FrameManager
     */
    friend class Core;    

    // Controllers
    SAP::IController* IPController = nullptr;
    SAP::IController* UARTController = nullptr;
    SAP::IController* RS485Controller = nullptr;

   public:
    
    enum ControllerType {ETHERNET, UART, RS485};


   private:
    // List of pendingConfirm IDs
    // std::list<SyndesiID*> pendingConfirm;

    /**
     * @brief Look in the pendingConfirm list and determine wether or not the
     * received ID is for a confirm
     *
     * @param id
     * @return true
     * @return false
     */
    bool inPendingConfirm(SyndesiID& id);

    void setCustomPort(unsigned short port);

    /*
     * Upper layer
     */
    SAP::IFrameManager_bottom* _frameManager;

    void registerFrameManager(SAP::IFrameManager_bottom* frameManager) {
        _frameManager = frameManager;
    };
    void registerController(SAP::IController* controller, ControllerType type);
    

    

    /*
     * Upper layers
     */
    bool request(Frame& frame);
    void response(Frame& frame);
    /*
     * Lower layers
     */
    // Data coming from the lower layer
    void controllerDataAvailable(SAP::IController* controller, SyndesiID& deviceID, size_t length);
    Frame readFrame(SyndesiID& id, SAP::IController* controller);    

   public:

    void setDefaultPort();
    unsigned short port();
};

}  // namespace syndesi

#endif  // NETWORK_INTERFACE_H
