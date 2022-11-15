#include <arpa/inet.h>
#include <netinet/in.h>
#include "syndesi.h"
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

void reg_write_callback(
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

int main() {
    syndesi::SyndesiID deviceID;

    core.callbacks.REGISTER_WRITE_16_reply_callback = reg_write_callback;
    core.init();

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
            ethernetController.waitForData();
            cout << "ok" << endl;
        }
        else {
            cout << "fail" << endl;
        }
        

        payload.address++;
        payload.data += 2;
        

        usleep(1'000'000); // 1s
    }
    return 0;
}


