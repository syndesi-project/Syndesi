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
#include "../core.h"

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
    int server_fd;
    int opt = 1;
    int new_socket;

    int sock = 0;

    struct sockaddr_in address;
    const int addrlen = sizeof(address);

    SyndesiID hostID;

   public:

   IPController() {
        syndesi::networkIPController = this;
    }

    void init() {

        if ((server_fd = socket(AF_INET, SOCK_STREAM, 0)) == 0) {
            perror("socket failed");
            exit(EXIT_FAILURE);
        }
        // Forcefully attaching socket to the port 8080
        if (setsockopt(server_fd, SOL_SOCKET, SO_REUSEADDR | SO_REUSEPORT, &opt,
                       sizeof(opt))) {
            perror("setsockopt");
            exit(EXIT_FAILURE);
        }

        address.sin_family = AF_INET;
        address.sin_addr.s_addr = INADDR_ANY;
        address.sin_port = htons(settings.getIPPort());

        if (bind(server_fd, (struct sockaddr*)&address, sizeof(address)) < 0) {
            perror("bind failed");
            exit(EXIT_FAILURE);
        }

        if (listen(server_fd, 3) < 0) {
            perror("listen");
            exit(EXIT_FAILURE);
        }
    }

    size_t write(SyndesiID& deviceID, char* buffer, size_t length) {
        int sock = 0;
        struct sockaddr_in serv_addr;

        serv_addr.sin_family = AF_INET;
        serv_addr.sin_port = htons(deviceID.getIPPort());
        if (inet_pton(AF_INET, deviceID.str().c_str(), &serv_addr.sin_addr) <= 0) {
            printf("\nInvalid address/ Address not supported \n");
            return 0;
        }

        size_t Nwritten = send(new_socket, buffer, length, 0);
        return Nwritten;
    }

    size_t read(char* buffer, size_t length) {
        int valread = ::read(new_socket, buffer, length);
        return valread;
    }

    void close() { ::close(new_socket); }

    void wait_for_connection() {
        if ((new_socket = accept(server_fd, (struct sockaddr*)&address,
                                 (socklen_t*)&addrlen)) < 0) {
            perror("accept");
            exit(EXIT_FAILURE);
        }
        hostID.fromIPv4(address.sin_addr.s_addr, address.sin_port);
        dataAvailable(hostID, -1);
        close();
    }    

    void end() { shutdown(server_fd, SHUT_RDWR); }
};
IPController ethernetController;

}

#endif // ETHERNET_SYSTEM_H