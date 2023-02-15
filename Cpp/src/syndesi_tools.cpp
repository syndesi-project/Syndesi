/**
 * @file syndesi_tools.cpp
 *
 * @brief Tools used by the Syndesi library
 *
 * @ingroup syndesi
 *
 * @author Sébastien Deriaz
 * @date 14.06.2022
 */


#include "syndesi_tools.h"

namespace syndesi {



size_t hton(const char* src, char* dest, size_t length) {
#if __BYTE_ORDER__ == __ORDER_BIG_ENDIAN__
    // System's endianness is the same as the network
    memcpy(dest, src, length);
#else
    // System's endianness is different from the network
    for (size_t i=0; i < length; i++) {
        dest[length-1-i] = src[i];
    }
#endif
    return length;
}

size_t ntoh(const char* src, char* dest, size_t length) {
    // The function is exactly the same as hton, they both exist for clarity reasons
    hton(src, dest, length);
    return length;
}
}