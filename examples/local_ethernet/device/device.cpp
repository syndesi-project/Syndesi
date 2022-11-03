#include <arpa/inet.h>
#include <stdio.h>
#include <string.h>
#include <sys/socket.h>
#include <unistd.h>

#include <cstdio>
#include <iostream>
#include <syndesi>

using namespace std;
using namespace syndesi;

syndesi::Core core;

void callback();

int new_socket;

syndesi::SyndesiID id;
class IPController : public syndesi::SAP::IController {
    int server_fd;
    int opt = 1;

    int sock = 0;

    struct sockaddr_in address;
    const int addrlen = sizeof(address);

    SyndesiID hostID;

   public:

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
        address.sin_port = htons(syndesi::settings.getIPPort());

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
        printf("ip controller write\n");
        int sock = 0;
        struct sockaddr_in serv_addr;

        serv_addr.sin_family = AF_INET;
        serv_addr.sin_port = htons(deviceID.getIPPort());
        if (inet_pton(AF_INET, deviceID.str().c_str(), &serv_addr.sin_addr) <= 0) {
            printf("\nInvalid address/ Address not supported \n");
            return 0;
        }

        size_t Nwritten = send(new_socket, buffer, length, 0);

        printf("write ok");

        return Nwritten;
    }

    size_t read(char* buffer, size_t length) {
        int valread = ::read(new_socket, buffer, length);

        /*for (int i = 0; i < valread; i++) {
            printf("%02X ", (uint8_t)buffer[i]);
        }*/
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

IPController controller;

int main(int argc, char const* argv[]) {
    char buffer[1024] = {0};

    cout << "Syndesi comtest example : device" << endl;
    cout << "Sébastien Deriaz    20.08.2022" << endl;

    core.addController(&controller, syndesi::Network::ControllerType::ETHERNET);
    controller.init();

    cout << "Listening for commands on port " << syndesi::settings.getIPPort() << " ..." << endl;

    while (1) {
        controller.wait_for_connection();
        cout << "ok" << endl;
    }

    return 0;
}

void syndesi::Callbacks::REGISTER_WRITE_16_request_callback(
    syndesi::REGISTER_WRITE_16_request& request,
    syndesi::REGISTER_WRITE_16_reply* reply) {
    cout << "REGISTER_WRITE_16_request_callback" << endl;
    cout << "    address = " << request.address << endl;
    cout << "    data = " << request.data << endl;
    cout << "    reply value : ok" << endl;
    reply->status = REGISTER_WRITE_16_reply::OK;
}