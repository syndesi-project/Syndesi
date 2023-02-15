/**
 * @file sdid.h
 *
 * @brief Syndesi ID library
 *
 * @ingroup syndesi
 *
 * @author Sébastien Deriaz
 * @date 14.08.2022
 */

/*
 * Syndesi unique ID (sdid) allows for the identification of devices and hosts
 *
 * Long version : 17 bytes long (to fit an IPv6 address alongside a header)
 * | header | IPv6 or other |
 * | 1 byte |    16 bytes   |
 *
 * Short version : 5 bytes long (to fit an IPv4 address alongside a header)
 * | header |  IPv4 or other |
 * | 1 byte |     4 bytes    |
 */

#ifndef SDID_H
#define SDID_H

#include <stdint.h>
#include <stdio.h>


#include "buffer.h"
#include "syndesi_tools.h"
#include "settings.h"

namespace syndesi {



/**
 * @brief Syndesi unique identifier for hosts and devices
 *
 */
class SyndesiID {
    // Friend so that the user can only see the class they're meant to
    friend class Network;
    friend class Core;
    friend class Frame;
    friend class IPController;
    friend class UARTController;
    friend class RS485Controller;
    friend class Controller;

    // Constants
    static const int IPv4_size = 4;
    static const int IPv6_size = 16;
    static const int IPv4_str_max_size = 16 + 1;
    static const char* no_address_string;

   
   public: // Public types
    
    enum address_type_t : unsigned char {
        None = 0,
        IPV4 = 1,
        IPV6 = 2};

   private: // Private types
    union Descriptor {
        unsigned char IPv4[IPv4_size];
        unsigned char IPv6[IPv6_size];
    } descriptor;
    unsigned short _port;
    union sdid_header_t {
        struct {
            address_type_t address_type : 4;
            bool follow : 1;
            unsigned char reserved : 3;
        } fields;
        unsigned char value;
    };

    const size_t addressSize(address_type_t type);

    bool operator==(SyndesiID& id);

   public: // User methods
    /**
     * @brief Default constructor
     *
     */
    SyndesiID();

    /**
     * @brief Parse an IPv4 address and check if it is valid or not. The format should be a.b.c.d
     * 
     * 
     * @param ip 
     * 
     * @return true if the IPv4 address is valid
     * @return false if the IPv4 address is invalid
     */
    bool parseIPv4(const char* ip, unsigned short port = 0);

    /**
     * @brief Create an IPv4 address from a uint32_t value
     * 
     * @param ip 32 bit unsigned integer
     */
    void fromIPv4(uint32_t ip, unsigned short port = 0);

    /**
     * @brief General ID parser
     * 
     * @param text 
     */
    bool parse(const char* text);


    /**
     * @brief Print device ID as string
     * 
     * @return string 
     */
    std::string str();

    

    /**
     * @brief Get the Address type
     *
     * @return address_type_t
     */
    address_type_t getAddressType();

    unsigned short getIPPort();

   private:
    /**
     * @brief Construct a new SyndesiID object from the given buffer and address
     * type
     *
     * @param buffer
     * @param type
     */
    SyndesiID(unsigned char* buffer, address_type_t type);


    /**
     * @brief Return a string description of the IPv4 address
     * 
     * @return string 
     */
    std::string IPv4str();

    void setIPPort(unsigned short port);

    /**
     * @brief Create a sub-SyndesiID object (adds at the end of the list)
     *
     * @param buffer
     * @param type
     */
    void append(unsigned char* buffer, address_type_t type);

    /**
     * @brief Construct a new SyndesiID object from an addressingHeader. The
     * resulting object is a child of a base SyndesiID object
     *
     * @param buffer
     *
     */
    SyndesiID(Buffer* buffer);

   public:
    /**
     * @brief Copy constructor
     *
     * @param sdid
     */
    SyndesiID(SyndesiID& sdid);

    //SyndesiID& operator=(const SyndesiID&) = default;

    /**
     * @brief Count the number re-routes (recursive)
     *
     */
    unsigned int reroutes();

   private:
    /**
     * @brief Gets the total adressing size, all addresses combined (recursive)
     *
     */
    size_t getTotalAdressingSize();

   private:
    /**
     * @brief Write Syndesi ID(s) to the given buffer
     *
     * @param buffer
     */
    void buildAddressingBuffer(Buffer* buffer);

    /**
     * @brief Read Syndesi ID(s) from the given buffer
     *
     * @param buffer
     */
    void parseAddressingBuffer(Buffer* buffer);

   private:
    // Next SyndesiID in case there's one (re-routing)
    SyndesiID* next = nullptr;
    sdid_header_t header;

    // If this object is a next of a previous SyndesiID
    // false only for the master
    bool is_next = false;
};
}  // namespace syndesi

#endif  // SDID_h
