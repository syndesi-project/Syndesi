/**
 * @file cinterface.cpp
 *
 * @brief Syndesi C-interface
 *
 * @author Sébastien Deriaz
 * @date 03.11.2022
 *
 *
 */

#include "cinterface.h"

extern "C" {
void* newCore() {
    syndesi::Core* core = new syndesi::Core();
    return core;
}

void delCore(void* core) {
    if (core != nullptr) {
        delete (syndesi::Core*)core;
    }
}
}