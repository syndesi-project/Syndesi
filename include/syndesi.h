/**
 * @file syndesi.h
 * @author Sébastien Deriaz
 * @brief Public header file
 * @version 0.1
 * @date 2022-08-09
 *
 * @copyright Copyright (c) 2022
 *
 */

#ifndef SYNDESI_H
#define SYNDESI_H

#include "callbacks.h"
#include "core.h"
#include "payloads.h"

#if !defined(SYNDESI_HOST_MODE) && !defined(SYNDESI_DEVICE_MODE)
    #error "MODE unspecified"
#endif


#endif  // SYNDESI_H