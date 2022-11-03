/**
 * @file cinterface.h
 *
 * @brief Syndesi C-interface
 *
 * @author Sébastien Deriaz
 * @date 03.11.2022
 * 
 * 
 * This interface is designed to allow usage of this library with python ctypes
 */

#ifndef CINTERFACE_H
#define CINTERFACE_H

#include "core.h"

// Core
extern "C" {
void* newCore();
void delCore(void* core);
}







#endif // CINTERFACE_H
