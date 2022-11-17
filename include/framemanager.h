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

    /*template <typename T>
    FrameManager& operator<<(T) {
        SAP::IInterpreter** interpreter = &first_interpreter;
        // T is a class
        // We navigate until we get to the last one
        while (*interpreter) {
            *interpreter = (*interpreter)->next;
        }
        *interpreter = new T();

        return *this;
    }*/

    FrameManager& operator<<(IInterpreter& new_interpreter) {
        // Add the interpreter to the list
        IInterpreter** interpreter = &first_interpreter;
        while (*interpreter) {
            *interpreter = (*interpreter)->next;
        }
        *interpreter = &new_interpreter;

        return *this;
    }

   private:
    /*
     * Upper layer
     */

    // void registerCallbacks(Callbacks* callbacks) { _callbacks = callbacks; };
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
