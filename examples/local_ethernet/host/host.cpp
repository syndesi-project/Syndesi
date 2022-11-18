#include <arpa/inet.h>
#include <netinet/in.h>
#include <sys/ioctl.h>
#include <sys/socket.h>
#include <unistd.h>

#include <iostream>
#include <limits>

#include "syndesi.h"
#include "interpreters/raw.h"
#include "ethernet/ethernethost.h"

#define DEVICE_IP "192.168.1.67"
//#define DEVICE_IP "127.0.0.1"

//#define CUSTOM_PORT 1234
//#define COMMAND_ID syndesi::cmt_t::REGISTER_READ_16

using namespace syndesi;

/*void reg_write_callback(RawInterpreter::RawPayloadReply& reply) {
    std::cout << "REGISTER_WRITE_16_reply_callback" << std::endl;
    std::cout << "    status = ";
    switch (reply.status) {
        case REGISTER_WRITE_16_reply::OK:
            cout << "ok";
            break;
        case REGISTER_WRITE_16_reply::NOK:
            cout << "nok";
            break;
    }
    cout << endl;
}*/

void error_callback(ErrorPayloadReply& reply) {
    printf("Error : %hu\n", reply.errorCode);
}

void raw_callback(RawInterpreter::RawPayloadReply& reply) {
    printf("Received data : \"");
    for(int i = 0;i<reply.data.length();i++) {
        printf("%02X ", (unsigned int)((unsigned char)reply.data[i]));
    }
    printf("\n");
}

int main() {
    SyndesiID deviceID;

    core.init();

    ErrorInterpreter error(error_callback);
    RawInterpreter raw(nullptr, raw_callback);

    core.frameManager << error << raw;

    cout << "Syndesi comtest example : host" << endl;
    cout << "Sébastien Deriaz    02.11.2022" << endl << endl;
    cout << "Sending periodic request to device at " << DEVICE_IP << endl;

    deviceID.parseIPv4(DEVICE_IP);

#ifdef CUSTOM_PORT
    controller.setCustomPort(CUSTOM_PORT);
#endif

    RawInterpreter::RawPayloadRequest payload;
    unsigned char buffer[] = {0x00, 0x10, 0x20, 0x30, 0x40, 0x50, 0x60, 0x70, 0x80};//, 0x90};
    payload.data = Buffer((char*)buffer, sizeof(buffer));

    printf("Payload (%u): ", payload.data.length());
    payload.data.print();
    printf("\n");
    
    //REGISTER_WRITE_16_request payload;
    //payload.address = 0;
    //payload.data = 0;

    //for(payload.data[0] = 0;payload.data[0]<100;payload.data[0]++) {
    while (true) {
        //cout << "send (address = " << payload.address
        //     << ", data = " << payload.data << ") ... ";

        if (core.sendRequest(payload, deviceID)) {
            ethernetController.waitForData();
            //cout << "ok" << endl;
        } else {
            cout << "fail" << endl;
        }

        payload.data[0]++;

        //payload.address++;
        //payload.data += 2;

        usleep(1'000);  // 1ms
    }
    return 0;
}
