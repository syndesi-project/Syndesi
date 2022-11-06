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

extern "C" {


/* Core */
void* newCore();
void delCore(void* core);
/* SyndesiID */
void* newSyndesiID();
void delSyndesiID(void* ID);
bool syndesiIDParseDescriptor(void* ID, const char* descriptor);
const char* syndesiIDString(void* ID);



}

#endif // CINTERFACE_H
