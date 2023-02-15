/**
 * @file syndesi.cpp
 *
 * @brief Syndesi device library
 *
 * @ingroup syndesi
 *
 * @author Sébastien Deriaz
 * @date 09.06.2022
 */

#include "core.h"

namespace syndesi {

Core core;

void Core::factory_init() {
    // register interfaces (connect layers together)

    // FrameManager class
    frameManager.registerNetwork(&network);
    // Network class
    network.registerFrameManager(&frameManager);
}

bool Core::sendRequest(IPayload& payload, SyndesiID& id) {
    // This version is easier but requires a copy of the SyndesiID argument
    Frame frame(id, payload);
    return frameManager.request(frame);
}

void Core::init() {
    factory_init();
    network.init();
}

}  // namespace syndesi