/**
 * @file system.h
 * @author Sébastien Deriaz
 * @brief System ethernet implementation
 * 
 * @date 03.11.2022
 *
 */


#ifndef ETHERNET_SYSTEM_H
#define ETHERNET_SYSTEM_H

#include "../interfaces.h"
#include "../sdid.h"
#include "../network.h"

#include <arpa/inet.h>
#include <stdio.h>
#include <string.h>
#include <sys/socket.h>
#include <unistd.h>
#include <netinet/in.h>
#include <sys/ioctl.h>

#include <cstdio>
#include <iostream>

namespace syndesi {

class IPController : public SAP::IController {
    int sock = 0;
    SyndesiID deviceID;

   public:
    IPController() {
        syndesi::networkIPController = this;
    }
    void init() { 
     }

    size_t write(SyndesiID& id, char* buffer, size_t length) {
        if ((sock = socket(AF_INET, SOCK_STREAM, 0)) < 0) {
            printf("Socket creation error \n");
            return 0;
        }

        struct sockaddr_in serv_addr;

        serv_addr.sin_family = AF_INET;
        serv_addr.sin_port = htons(id.getIPPort());
        if (inet_pton(AF_INET, id.str().c_str(), &serv_addr.sin_addr) <= 0) {
            printf("Invalid address/ Address not supported \n");
            return 0;
        }

        if (connect(sock, (struct sockaddr*)&serv_addr, sizeof(serv_addr)) <
            0) {
            printf("Connection Failed\n");
            return 0;
        }

        printf("Socket write\n");
        for(int i = 0;i<length;i++) {
            printf("%02X ", (unsigned int)(buffer[i]));
        }
        printf("\n");

        return send(sock, buffer, length, 0);
    }

    size_t read(char* buffer, size_t length) {
        int valread = ::read(sock, buffer, length);
        return valread;
    }

    void close() { ::close(sock); }

    SyndesiID& getSyndesiID() { return deviceID; }

    void waitForData() {
        int count = 0;
        do {
            ioctl(sock, FIONREAD, &count);
        } while (count <= 0);
        dataAvailable(deviceID, count);
        close();
    }
};

IPController ethernetController;

}

#endif // ETHERNET_SYSTEM_H