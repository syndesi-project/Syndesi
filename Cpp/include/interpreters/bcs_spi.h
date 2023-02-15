/**
 * @file bcs_spi.h
 *
 * @brief Basic Command Set SPI interpreter
 *
 * @author Sébastien Deriaz
 * @date 16.11.2022
 */

#ifndef SPI_INTERPRETER_H
#define SPI_INTERPRETER_H

#include "../iinterpreter.h"
#include "../payload.h"

namespace syndesi {


class SPIPayload : public Payload {
    void build(Buffer& dest) {
        dest.data();
    }
    size_t length() {
        return 10;
    }
};

class SPIInterpreter : SAP::IInterpreter {
   public:
    bool parse(Buffer& payload) {
        // parse
        return true;
    }
    Payload* reply() {
        SPIPayload* spi = new SPIPayload();
        return spi;
    }
};

}  // namespace syndesi

#endif  // SPI_INTERPRETER_H