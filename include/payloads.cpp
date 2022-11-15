/* THIS FILE IS GENERATED AUTOMATICALLY
 *  DO NOT EDIT
 *  This file has been written by the script generate_commands.py
 *  date : 22-11-15 10:03:28
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

Payload* newPayloadInstance(cmd_t id, bool request_nReply) {

    if(request_nReply) {
        switch(id) {
        case 0x0002:
            return new DEVICE_DISCOVER_request();
            break;
        case 0x0100:
            return new REGISTER_READ_16_request();
            break;
        case 0x0101:
            return new REGISTER_WRITE_16_request();
            break;
        case 0x0110:
            return new SPI_READ_WRITE_request();
            break;
        case 0x0111:
            return new SPI_WRITE_ONLY_request();
            break;
        case 0x0120:
            return new I2C_READ_request();
            break;
        case 0x0121:
            return new I2C_WRITE_request();
            break;

        default:
            return nullptr;
            break;
        }
    }
    else {
        switch(id) {
        case 0x0001:
            return new ERROR_reply();
            break;
        case 0x0002:
            return new DEVICE_DISCOVER_reply();
            break;
        case 0x0100:
            return new REGISTER_READ_16_reply();
            break;
        case 0x0101:
            return new REGISTER_WRITE_16_reply();
            break;
        case 0x0110:
            return new SPI_READ_WRITE_reply();
            break;
        case 0x0111:
            return new SPI_WRITE_ONLY_reply();
            break;
        case 0x0120:
            return new I2C_READ_reply();
            break;
        case 0x0121:
            return new I2C_WRITE_reply();
            break;

        default:
            return nullptr;
            break;
        }
    }
}

} //namespace syndesi