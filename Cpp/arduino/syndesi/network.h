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



#include "linkedlist.h"

#ifdef ARDUINO
#include <Arduino.h>
#define SLEEP(x) delay(x)
#else
#include <unistd.h>
#define SLEEP(x) usleep((x)*1000)
#endif

using namespace std;

namespace syndesi {

// Why Global ?
// Because when the driver is created, especially a pre-made one, we do not want to
// tell the user "do a controller.init()" to connect the controller to the network class.
// So we make this connection in the controller's constructor. But we can't be sure that the
// network's constructor is done yet (and indeed, after testing, it isn't).
// In the end this is the best solution, the controller can "register" itself on the global variable
// 
extern SAP::IController* networkIPController;
extern SAP::IController* networkUARTController;
extern SAP::IController* networkRS485Controller;

class Network : SAP::INetwork_top, public SAP::INetwork_bottom {
    /**
     * @brief Network frame instance
     * @note contains a network header and a payload. The payload is forwarded
     * to the FrameManager
     */
    friend class Core;

    public:
    Network() {}

    LinkedList<SyndesiID> devicesList;
    

   public:
    enum ControllerType { ETHERNET, UART, RS485 };

    //void registerController(SAP::IController* controller, ControllerType type);

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
    SAP::IFrameManager_bottom* _frameManager = nullptr;

    void registerFrameManager(SAP::IFrameManager_bottom* frameManager) {
        _frameManager = frameManager;
    };

    /*
     * Upper layers
     */
    bool request(Frame& frame);
    void response(Frame& frame);
    /*
     * Lower layers
     */
    // Data coming from the lower layer
    void controllerDataAvailable(SAP::IController* controller,
                                 SyndesiID& deviceID, size_t length);
    Frame readFrame(SyndesiID& id, SAP::IController* controller);

   public:
    void setDefaultPort();
    unsigned short port();

    void init();
};

}  // namespace syndesi

#endif  // NETWORK_INTERFACE_H
