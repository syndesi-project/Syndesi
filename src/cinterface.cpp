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
#include <iostream>

extern "C" {
/* Core */
void* newCore() {
    syndesi::Core* core = new syndesi::Core();
    return core;
}

void delCore(void* core) {
    if (core != nullptr) {
        delete (syndesi::Core*)core;
    }
}

/* SyndesiID */
void* newSyndesiID() {
    syndesi::SyndesiID* ID = new syndesi::SyndesiID();
    return ID;
}
void delSyndesiID(void* ID) {
    if (ID != nullptr) {
        delete (syndesi::SyndesiID*)ID;
    }
}
bool syndesiIDParseDescriptor(void* ID, const char* descriptor) {
    if (ID != nullptr) {
        return ((syndesi::SyndesiID*)ID)->parse(descriptor);
    }
    return false;
}
const char* syndesiIDString(void* ID) {
    char* output = nullptr;
    if (ID != nullptr) {
        std::string temp = ((syndesi::SyndesiID*)ID)->str();
        output = (char*)malloc(temp.size());
        if (output != nullptr) {
            temp.copy(output, temp.size());
        }
    }
    return output;
}
}