/**
 * @file framemanager.cpp
 *
 * @brief Management of frames
 *
 * @author Sébastien Deriaz
 * @date 15.08.2022
 */

#include "framemanager.h"

namespace syndesi {
/*
 * Upper layer
 */
bool FrameManager::request(Frame& frame) {
    if (network != nullptr) {
        return network->request(frame);
    }
    return false;
}

}  // namespace syndesi