/* THIS FILE IS GENERATED AUTOMATICALLY
 *  DO NOT EDIT
 *  This file has been written by the script generate_commands.py
 *  date : 22-11-15 10:03:28
 */


#ifndef COMMANDS_H
#define COMMANDS_H

#include <stdint.h>
#include "syndesi_tools.h"
#include "buffer.h"
//#include <memory>

namespace syndesi {

typedef uint16_t cmd_t;

enum commands : cmd_t {
    NO_COMMAND = 0x0000,
    ERROR = 0x0001,
    DEVICE_DISCOVER = 0x0002,
    REGISTER_READ_16 = 0x0100,
    REGISTER_WRITE_16 = 0x0101,
    SPI_READ_WRITE = 0x0110,
    SPI_WRITE_ONLY = 0x0111,
    I2C_READ = 0x0120,
    I2C_WRITE = 0x0121
};


class Payload {
    friend class Frame;
   protected:
    virtual void build(Buffer* buffer) = 0;
    virtual size_t payloadLength() = 0;
    virtual cmd_t getCommand() = 0;
};

extern const cmd_t commandIDArray[];

const char* commandNameByID(cmd_t id);

Payload* newPayloadInstance(cmd_t id, bool request_nReply);

class ERROR_reply : public Payload{
friend class FrameManager;
public:
    enum error_code_t {INVALID_FRAME=0, OTHER=1, NO_CALLBACK=2} error_code;


    ERROR_reply() {};
private:

ERROR_reply(Buffer* payloadBuffer) {
        size_t pos = 0;
                pos += ntoh(payloadBuffer->data() + pos, reinterpret_cast<char*>(&error_code), 1);
 
    };

    cmd_t getCommand() {return 0x0001;}    



    size_t payloadLength() {
        return 1;
    }

    void build(Buffer* payloadBuffer) {
        size_t pos = 0;
        pos += hton(reinterpret_cast<char*>(&error_code), payloadBuffer->data() + pos, 1);

    }
};

class DEVICE_DISCOVER_request : public Payload{
friend class FrameManager;
public:


    DEVICE_DISCOVER_request() {};
private:

DEVICE_DISCOVER_request(Buffer* payloadBuffer) {
        size_t pos = 0;
         
    };

    cmd_t getCommand() {return 0x0002;}    



    size_t payloadLength() {
        return 0;
    }

    void build(Buffer* payloadBuffer) {
        size_t pos = 0;

    }
};

class DEVICE_DISCOVER_reply : public Payload{
friend class FrameManager;
public:
    Buffer ID;
    uint32_t syndesi_protocol_version;
    uint32_t device_version;
    uint32_t name_length;
    Buffer name;
    uint32_t description_length;
    Buffer description;


    DEVICE_DISCOVER_reply() {};
private:

DEVICE_DISCOVER_reply(Buffer* payloadBuffer) {
        size_t pos = 0;
                ID.fromParent(payloadBuffer, pos, 20);        pos += 20;        pos += ntoh(payloadBuffer->data() + pos, reinterpret_cast<char*>(&syndesi_protocol_version), 4);
        pos += ntoh(payloadBuffer->data() + pos, reinterpret_cast<char*>(&device_version), 4);
        pos += ntoh(payloadBuffer->data() + pos, reinterpret_cast<char*>(&name_length), 4);
        name.fromParent(payloadBuffer, pos, name_length);        pos += name_length;        pos += ntoh(payloadBuffer->data() + pos, reinterpret_cast<char*>(&description_length), 4);
        description.fromParent(payloadBuffer, pos, description_length);        pos += description_length; 
    };

    cmd_t getCommand() {return 0x0002;}    



    size_t payloadLength() {
        return 20 + 4 + 4 + 4 + name_length + 4 + description_length;
    }

    void build(Buffer* payloadBuffer) {
        size_t pos = 0;
        pos += hton(reinterpret_cast<char*>(&syndesi_protocol_version), payloadBuffer->data() + pos, 4);
        pos += hton(reinterpret_cast<char*>(&device_version), payloadBuffer->data() + pos, 4);
        pos += hton(reinterpret_cast<char*>(&name_length), payloadBuffer->data() + pos, 4);
        pos += hton(reinterpret_cast<char*>(&description_length), payloadBuffer->data() + pos, 4);

    }
};

class REGISTER_READ_16_request : public Payload{
friend class FrameManager;
public:
    uint32_t address;


    REGISTER_READ_16_request() {};
private:

REGISTER_READ_16_request(Buffer* payloadBuffer) {
        size_t pos = 0;
                pos += ntoh(payloadBuffer->data() + pos, reinterpret_cast<char*>(&address), 4);
 
    };

    cmd_t getCommand() {return 0x0100;}    



    size_t payloadLength() {
        return 4;
    }

    void build(Buffer* payloadBuffer) {
        size_t pos = 0;
        pos += hton(reinterpret_cast<char*>(&address), payloadBuffer->data() + pos, 4);

    }
};

class REGISTER_READ_16_reply : public Payload{
friend class FrameManager;
public:
    uint32_t data;


    REGISTER_READ_16_reply() {};
private:

REGISTER_READ_16_reply(Buffer* payloadBuffer) {
        size_t pos = 0;
                pos += ntoh(payloadBuffer->data() + pos, reinterpret_cast<char*>(&data), 4);
 
    };

    cmd_t getCommand() {return 0x0100;}    



    size_t payloadLength() {
        return 4;
    }

    void build(Buffer* payloadBuffer) {
        size_t pos = 0;
        pos += hton(reinterpret_cast<char*>(&data), payloadBuffer->data() + pos, 4);

    }
};

class REGISTER_WRITE_16_request : public Payload{
friend class FrameManager;
public:
    uint32_t address;
    uint32_t data;


    REGISTER_WRITE_16_request() {};
private:

REGISTER_WRITE_16_request(Buffer* payloadBuffer) {
        size_t pos = 0;
                pos += ntoh(payloadBuffer->data() + pos, reinterpret_cast<char*>(&address), 4);
        pos += ntoh(payloadBuffer->data() + pos, reinterpret_cast<char*>(&data), 4);
 
    };

    cmd_t getCommand() {return 0x0101;}    



    size_t payloadLength() {
        return 4 + 4;
    }

    void build(Buffer* payloadBuffer) {
        size_t pos = 0;
        pos += hton(reinterpret_cast<char*>(&address), payloadBuffer->data() + pos, 4);
        pos += hton(reinterpret_cast<char*>(&data), payloadBuffer->data() + pos, 4);

    }
};

class REGISTER_WRITE_16_reply : public Payload{
friend class FrameManager;
public:
    enum status_t {OK=0, NOK=1} status;


    REGISTER_WRITE_16_reply() {};
private:

REGISTER_WRITE_16_reply(Buffer* payloadBuffer) {
        size_t pos = 0;
                pos += ntoh(payloadBuffer->data() + pos, reinterpret_cast<char*>(&status), 1);
 
    };

    cmd_t getCommand() {return 0x0101;}    



    size_t payloadLength() {
        return 1;
    }

    void build(Buffer* payloadBuffer) {
        size_t pos = 0;
        pos += hton(reinterpret_cast<char*>(&status), payloadBuffer->data() + pos, 1);

    }
};

class SPI_READ_WRITE_request : public Payload{
friend class FrameManager;
public:
    uint32_t interface_index;
    uint32_t write_size;
    Buffer write_data;


    SPI_READ_WRITE_request() {};
private:

SPI_READ_WRITE_request(Buffer* payloadBuffer) {
        size_t pos = 0;
                pos += ntoh(payloadBuffer->data() + pos, reinterpret_cast<char*>(&interface_index), 4);
        pos += ntoh(payloadBuffer->data() + pos, reinterpret_cast<char*>(&write_size), 4);
        write_data.fromParent(payloadBuffer, pos, write_size);        pos += write_size; 
    };

    cmd_t getCommand() {return 0x0110;}    



    size_t payloadLength() {
        return 4 + 4 + write_size;
    }

    void build(Buffer* payloadBuffer) {
        size_t pos = 0;
        pos += hton(reinterpret_cast<char*>(&interface_index), payloadBuffer->data() + pos, 4);
        pos += hton(reinterpret_cast<char*>(&write_size), payloadBuffer->data() + pos, 4);

    }
};

class SPI_READ_WRITE_reply : public Payload{
friend class FrameManager;
public:
    uint32_t read_size;
    Buffer read_data;


    SPI_READ_WRITE_reply() {};
private:

SPI_READ_WRITE_reply(Buffer* payloadBuffer) {
        size_t pos = 0;
                pos += ntoh(payloadBuffer->data() + pos, reinterpret_cast<char*>(&read_size), 4);
        read_data.fromParent(payloadBuffer, pos, read_size);        pos += read_size; 
    };

    cmd_t getCommand() {return 0x0110;}    



    size_t payloadLength() {
        return 4 + read_size;
    }

    void build(Buffer* payloadBuffer) {
        size_t pos = 0;
        pos += hton(reinterpret_cast<char*>(&read_size), payloadBuffer->data() + pos, 4);

    }
};

class SPI_WRITE_ONLY_request : public Payload{
friend class FrameManager;
public:
    uint32_t interface_index;
    uint32_t write_size;
    Buffer write_data;


    SPI_WRITE_ONLY_request() {};
private:

SPI_WRITE_ONLY_request(Buffer* payloadBuffer) {
        size_t pos = 0;
                pos += ntoh(payloadBuffer->data() + pos, reinterpret_cast<char*>(&interface_index), 4);
        pos += ntoh(payloadBuffer->data() + pos, reinterpret_cast<char*>(&write_size), 4);
        write_data.fromParent(payloadBuffer, pos, write_size);        pos += write_size; 
    };

    cmd_t getCommand() {return 0x0111;}    



    size_t payloadLength() {
        return 4 + 4 + write_size;
    }

    void build(Buffer* payloadBuffer) {
        size_t pos = 0;
        pos += hton(reinterpret_cast<char*>(&interface_index), payloadBuffer->data() + pos, 4);
        pos += hton(reinterpret_cast<char*>(&write_size), payloadBuffer->data() + pos, 4);

    }
};

class SPI_WRITE_ONLY_reply : public Payload{
friend class FrameManager;
public:
    enum status_t {OK=0, NOK=1} status;


    SPI_WRITE_ONLY_reply() {};
private:

SPI_WRITE_ONLY_reply(Buffer* payloadBuffer) {
        size_t pos = 0;
                pos += ntoh(payloadBuffer->data() + pos, reinterpret_cast<char*>(&status), 1);
 
    };

    cmd_t getCommand() {return 0x0111;}    



    size_t payloadLength() {
        return 1;
    }

    void build(Buffer* payloadBuffer) {
        size_t pos = 0;
        pos += hton(reinterpret_cast<char*>(&status), payloadBuffer->data() + pos, 1);

    }
};

class I2C_READ_request : public Payload{
friend class FrameManager;
public:
    uint32_t interface_index;
    uint32_t read_size;


    I2C_READ_request() {};
private:

I2C_READ_request(Buffer* payloadBuffer) {
        size_t pos = 0;
                pos += ntoh(payloadBuffer->data() + pos, reinterpret_cast<char*>(&interface_index), 4);
        pos += ntoh(payloadBuffer->data() + pos, reinterpret_cast<char*>(&read_size), 4);
 
    };

    cmd_t getCommand() {return 0x0120;}    



    size_t payloadLength() {
        return 4 + 4;
    }

    void build(Buffer* payloadBuffer) {
        size_t pos = 0;
        pos += hton(reinterpret_cast<char*>(&interface_index), payloadBuffer->data() + pos, 4);
        pos += hton(reinterpret_cast<char*>(&read_size), payloadBuffer->data() + pos, 4);

    }
};

class I2C_READ_reply : public Payload{
friend class FrameManager;
public:
    uint32_t read_size;
    Buffer read_data;


    I2C_READ_reply() {};
private:

I2C_READ_reply(Buffer* payloadBuffer) {
        size_t pos = 0;
                pos += ntoh(payloadBuffer->data() + pos, reinterpret_cast<char*>(&read_size), 4);
        read_data.fromParent(payloadBuffer, pos, read_size);        pos += read_size; 
    };

    cmd_t getCommand() {return 0x0120;}    



    size_t payloadLength() {
        return 4 + read_size;
    }

    void build(Buffer* payloadBuffer) {
        size_t pos = 0;
        pos += hton(reinterpret_cast<char*>(&read_size), payloadBuffer->data() + pos, 4);

    }
};

class I2C_WRITE_request : public Payload{
friend class FrameManager;
public:
    uint32_t interface_index;
    uint32_t write_size;
    Buffer write_data;


    I2C_WRITE_request() {};
private:

I2C_WRITE_request(Buffer* payloadBuffer) {
        size_t pos = 0;
                pos += ntoh(payloadBuffer->data() + pos, reinterpret_cast<char*>(&interface_index), 4);
        pos += ntoh(payloadBuffer->data() + pos, reinterpret_cast<char*>(&write_size), 4);
        write_data.fromParent(payloadBuffer, pos, write_size);        pos += write_size; 
    };

    cmd_t getCommand() {return 0x0121;}    



    size_t payloadLength() {
        return 4 + 4 + write_size;
    }

    void build(Buffer* payloadBuffer) {
        size_t pos = 0;
        pos += hton(reinterpret_cast<char*>(&interface_index), payloadBuffer->data() + pos, 4);
        pos += hton(reinterpret_cast<char*>(&write_size), payloadBuffer->data() + pos, 4);

    }
};

class I2C_WRITE_reply : public Payload{
friend class FrameManager;
public:
    enum status_t {OK=0, NOK=1} status;


    I2C_WRITE_reply() {};
private:

I2C_WRITE_reply(Buffer* payloadBuffer) {
        size_t pos = 0;
                pos += ntoh(payloadBuffer->data() + pos, reinterpret_cast<char*>(&status), 1);
 
    };

    cmd_t getCommand() {return 0x0121;}    



    size_t payloadLength() {
        return 1;
    }

    void build(Buffer* payloadBuffer) {
        size_t pos = 0;
        pos += hton(reinterpret_cast<char*>(&status), payloadBuffer->data() + pos, 1);

    }
};



}  // namespace syndesi

#endif  // COMMANDS_H