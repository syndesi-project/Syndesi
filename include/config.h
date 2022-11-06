/**
 * @file config.h
 *
 * @brief Management of the syndesi_config.h file
 * if the file is included or not (see __has_include)
 *
 * @author Sébastien Deriaz
 * @date 16.08.2022
 */

/*
 * NOTE : There are two ways of configuring the library
 *
 * 1) Including a syndesi_config.h file inside your build directory and let the
 * library find it 2) Include the syndesi_config.h FIRST and then include the
 * syndesi.h library. This method is used with Arduino because it cannot use
 * the __has_include directive
 */

#define SYNDESI

#ifdef SYNDESI_CONFIG_INCLUDED
// The syndesi_config.h file is already included, nothing to do
#elif __has_include("syndesi_config.h")
// We need to find ourselves
//#error "include file"
#include "syndesi_config.h"
#else
// The config file wasn't included first, this file tried looking for it but no
// luck, so we throw an error
#error \
    "syndesi_config.h file wasn't included and wasn't found in the include directories either"
#endif