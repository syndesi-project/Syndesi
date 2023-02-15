/* THIS FILE IS GENERATED AUTOMATICALLY
 *  DO NOT EDIT
 *  This file has been written by the script generate_commands.py
 *  date : 22-11-15 10:03:28
 *
 *  Template :
 * @file framemanager.h
 *
 * @brief Management of frames
 *
 * @author Sébastien Deriaz
 * @date 15.08.2022
 */

#ifndef FRAME_MANAGER_H
#define FRAME_MANAGER_H

#include "inetwork_top.h"
#include "interfaces.h"
#include "iinterpreter.h"

#include "interpreters/error.h"

using namespace std;

#ifdef ARDUINO
#include <Arduino.h>
#define SLEEP(x) delay(x)
#else
#include <unistd.h>
#define SLEEP(x) usleep((x)*1000)
#endif

namespace syndesi {

/**
 * @brief Class to manage frames after they've been parsed by the network
 * interface
 *
 */

class FrameManager : SAP::IFrameManager_bottom, SAP::IFrameManager_top {
    friend class Core;

   public:
    FrameManager(){};
    ~FrameManager(){};

    IInterpreter* first_interpreter = nullptr;

    FrameManager& operator<<(IInterpreter& new_interpreter);

   private:
    /*
     * Upper layer
     */
    //  From core
    bool request(Frame& frame);
    /*
     * Lower layer
     */
    SAP::INetwork_top* network = nullptr;
    void registerNetwork(SAP::INetwork_top* _network) { network = _network; };

    /* Indication (incoming from host)*/
    void indication(Frame& frame);

    /* Confirm (incoming from device)*/
    void confirm(Frame& frame);
};

}  // namespace syndesi

#endif  // FRAME_MANAGER_H
