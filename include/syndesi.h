/**
 * @file syndesi.h
 * @author Sébastien Deriaz
 * @brief Public header file
 * 
 * @date 2022-08-09
 *
 */

#ifndef SYNDESI_H
#define SYNDESI_H

#include "config.h"

#if !defined(SYNDESI_HOST_MODE) && !defined(SYNDESI_DEVICE_MODE)
    #error "MODE unspecified"
#endif

#include "callbacks.h"
#include "core.h"
#include "payloads.h"
#include "framemanager.h"

#if !defined(SYNDESI_ETHERNET_CONTROLLER)
    #error "Ehernet controller must be specified"
#endif

#if SYNDESI_ETHERNET_CONTROLLER == 1
    #include "ethernet/systemethernet.h"
#endif

#endif  // SYNDESI_H