/**
 * @file sdid.cpp
 *
 * @brief Syndesi ID library
 *
 * @ingroup syndesi
 *
 * @author Sébastien Deriaz
 * @date 14.08.2022
 */

#include "sdid.h"

namespace syndesi {

const char* SyndesiID::no_address_string = "no address";

/*
 * User methods
 */
SyndesiID::SyndesiID() {}

bool SyndesiID::parseIPv4(const char* ip, unsigned short port) {
    unsigned int count = 0;
    unsigned char bytes[IPv4_size];
    for (int i = 0, r = 0; i < IPv4_size; ip += r + 1, i++) {
        if (sscanf(ip, "%d%n", &bytes[i], &r) < 0) {
            return false;
        }
    }
    // Valid IP
    if (port > 0) _port = port;
    else _port = settings.getIPPort(); // This works only for devices
    memcpy(&payload.IPv4, bytes, IPv4_size);
    header.fields.address_type = IPV4;
    return true;
}

void SyndesiID::fromIPv4(uint32_t ip, unsigned short port) {
    // TODO : check for endianness
    memcpy(&payload, &ip, IPv4_size);
    if (port > 0) _port = port;
    header.fields.address_type = IPV4;
}

std::string SyndesiID::str() {
    switch (getAddressType()) {
        case IPV4:
            return IPv4str();
            break;
        default:
            return no_address_string;
    }
}

unsigned short SyndesiID::getIPPort() { return _port; }

/*
 * Private methods
 */

std::string SyndesiID::IPv4str() {
    std::string output;
    for(int i = 0;i < IPv4_size;i++) {
        if (i > 0) {
            output += ".";
        }
        output += INT_TO_STRING(payload.IPv4[i]);
    }
    return output;
}

SyndesiID::SyndesiID(unsigned char* buffer, address_type_t type) {
    header.fields.address_type = type;
    header.fields.follow = false;
    header.fields.reserved = 0;
    switch (type) {
        case IPV4:
        case IPV6:
            memcpy((void*)&payload, buffer, addressSize(type));
            break;
    }
}

void SyndesiID::setIPPort(unsigned short port) { _port = port; }

void SyndesiID::append(unsigned char* buffer, address_type_t type) {
    if (next) {
        // Add to the next one
        next->append(buffer, type);
    } else {
        // Add here
        next = new SyndesiID(buffer, type);
    }
}

SyndesiID::SyndesiID(SyndesiID& sdid) {
    memcpy(&payload, &sdid.payload, sizeof(sdid.payload));
    header.value = sdid.header.value;
}

SyndesiID::SyndesiID(Buffer* buffer) {
    // Read the header
    ntoh(buffer->data(), reinterpret_cast<char*>(&header), sizeof(header));
    // Read the payload
    size_t address_size = addressSize(header.fields.address_type);
    memcpy(reinterpret_cast<void*>(&payload), buffer->data() + sizeof(header),
           address_size);
    is_next = true;
    if (header.fields.follow) {
        Buffer subbuffer = Buffer(buffer, address_size + sizeof(header));
        next = new SyndesiID(&subbuffer);
    }
}

unsigned int SyndesiID::reroutes() {
    size_t count = 0;
    if (next) {
        count += next->reroutes();
    }
    return count;
}

const size_t SyndesiID::addressSize(address_type_t type) {
    switch (type) {
        case IPV4:
            return IPv4_size;
        case IPV6:
            return IPv6_size;
        default:
            return 0;
    }
}

size_t SyndesiID::getTotalAdressingSize() {
    size_t size = 0;
    if (is_next) addressSize(header.fields.address_type);
    if (next) size += next->getTotalAdressingSize();
    return size;
}

SyndesiID::address_type_t SyndesiID::getAddressType() {
    return header.fields.address_type;
}

void SyndesiID::buildAddressingBuffer(Buffer* buffer) {
    // Do not write itself
    size_t addressLength = 0;
    size_t offset = 0;
    if (is_next) {
        // Write itself
        hton(reinterpret_cast<char*>(&header), buffer->data(), sizeof(header));
        addressLength = addressSize(header.fields.address_type);
        memcpy(buffer->data() + sizeof(header), &payload, addressLength);
        if (next) {
            // As long as they are "next"s, write them
            Buffer subbuffer(buffer, addressLength + sizeof(header));
            next->buildAddressingBuffer(&subbuffer);
        }
    } else if (next) {
        // Do not write the master, but start with the first "next"
        next->buildAddressingBuffer(buffer);
    }
}

void SyndesiID::parseAddressingBuffer(Buffer* buffer) {
    // Read
    next = new SyndesiID(buffer);
}
}  // namespace syndesi
