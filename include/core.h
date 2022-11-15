/**
 * @file core.h
 *
 * @brief Syndesi core
 *
 * @author Sébastien Deriaz
 * @date 09.08.2022
 */

#ifndef CORE_H
#define CORE_H

#include "callbacks.h"
#include "frame.h"
#include "framemanager.h"
#include "network.h"
#include "settings.h"

namespace syndesi {

class Core {
   private:
    void factory_init();

    /*
     * Layers
     */
    public: // making it public temporarily
    Callbacks callbacks;
    FrameManager frameManager;
    Network network;


   public:
    bool sendRequest(Payload& payload, SyndesiID& id);

    Core() {}
    ~Core(){};


    void init();
};

extern Core core;

}  // namespace syndesi

#endif  // CORE_H