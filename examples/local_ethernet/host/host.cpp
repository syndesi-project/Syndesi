#include <arpa/inet.h>
#include <netinet/in.h>
#include <syndesi>
#include <sys/ioctl.h>
#include <sys/socket.h>
#include <unistd.h>

#include <iostream>
#include <limits>


#define DEVICE_IP "127.0.0.1"
//#define CUSTOM_PORT 1234
#define COMMAND_ID syndesi::cmt_t::REGISTER_READ_16



using namespace std;
using namespace syndesi;

Core core;

class IPController : public SAP::IController {
    int sock = 0;
    SyndesiID deviceID;

   public:
    void init() { cout << "init, socket = " << sock << endl; }

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

        return send(sock, buffer, length, 0);
    }

    size_t read(char* buffer, size_t length) {
        int valread = ::read(sock, buffer, length);
        /*for (int i = 0; i < valread; i++) {
            printf("%02X ", (uint8_t)buffer[i]);
        }*/
        return valread;
    }

    void close() { ::close(sock); }

    SyndesiID& getSyndesiID() { return deviceID; }

    void waitForData() {
        int count = 0;
        do {
            ioctl(sock, FIONREAD, &count);
        } while (count <= 0);
        printf("count = %d", count);
        dataAvailable(deviceID, count);
        close();
    }
};

/**
 * @brief Send command with the desired ID
 *
 * @param commandID
 * @return true if the ID is valid
 * @return false if the ID is invalid
 */
bool sendCommand(cmd_t commandID);

IPController controller;

syndesi::SyndesiID deviceID;

int main() {
    struct sockaddr_in address;
    char buffer[1024] = {0};
    int choice;
    

    core.addController(&controller, Network::ControllerType::ETHERNET);
    controller.init();


    bool validIPAddress = true;

    cout << "Syndesi comtest example : host" << endl;
    cout << "Sébastien Deriaz    02.11.2022" << endl << endl;
    cout << "Sending periodic request to device at " << DEVICE_IP << endl;
    

    deviceID.parseIPv4(DEVICE_IP);

#ifdef CUSTOM_PORT
    controller.setCustomPort(CUSTOM_PORT);
#endif

    REGISTER_WRITE_16_request payload;
    payload.address = 0;
    payload.data = 0;

    while(true) {
        cout << "send (address = " << payload.address << ", data = " << payload.data << ") ... ";
        if(core.sendRequest(payload, deviceID)) {
            cout << "ok" << endl;
            controller.waitForData();
        }
        else {
            cout << " fail" << endl;
        }
        

        payload.address++;
        payload.data += 2;
        

        usleep(1'000'000); // 1s
    }
    return 0;
}

void syndesi::Callbacks::REGISTER_WRITE_16_reply_callback(
    syndesi::REGISTER_WRITE_16_reply& reply) {
    cout << "REGISTER_WRITE_16_reply_callback" << endl;
    cout << "    status = ";
    switch (reply.status) {
        case REGISTER_WRITE_16_reply::OK:
            cout << "ok";
            break;
        case REGISTER_WRITE_16_reply::NOK:
            cout << "nok";
            break;
    }
    cout << endl;
}