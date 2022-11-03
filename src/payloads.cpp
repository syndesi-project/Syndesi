/* THIS FILE IS GENERATED AUTOMATICALLY
 *  DO NOT EDIT
 *  This file has been written by the script generate_commands.py
 *  date : 22-11-01 15:11:23
 */


#include "payloads.h"

namespace syndesi {

const cmd_t commandIDArray[] = {
0x0000,
0x0001,
0x0002,
0x0100,
0x0101,
0x0110,
0x0111,
0x0120,
0x0121
};

const char* commandNameByID(cmd_t id) {
    switch(id) {
        case 0x0000:
            return "NO_COMMAND";
            break;
        case 0x0001:
            return "ERROR";
            break;
        case 0x0002:
            return "DEVICE_DISCOVER";
            break;
        case 0x0100:
            return "REGISTER_READ_16";
            break;
        case 0x0101:
            return "REGISTER_WRITE_16";
            break;
        case 0x0110:
            return "SPI_READ_WRITE";
            break;
        case 0x0111:
            return "SPI_WRITE_ONLY";
            break;
        case 0x0120:
            return "I2C_READ";
            break;
        case 0x0121:
            return "I2C_WRITE";
            break;

        default:
            return "";
            break;
    }
}

} //namespace syndesi