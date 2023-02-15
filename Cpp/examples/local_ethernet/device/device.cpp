#include <arpa/inet.h>
#include <stdio.h>
#include <string.h>
#include <sys/socket.h>
#include <unistd.h>

#include <cstdio>
#include <iostream>

#include "syndesi.h"
#include "interpreters/raw.h"
#include "ethernet/ethernetdevice.h"

using namespace std;
using namespace syndesi;

bool quit = false;

void raw_callback(RawInterpreter::RawPayloadRequest& request, RawInterpreter::RawPayloadReply* reply) {
    printf("Received raw payload : \"");
    reply->data.allocate(2);
    /*reply->data = Buffer(request.data.length());
    for(int i = 0;i<request.data.length();i++) {
        printf("%02X ", (unsigned int)((unsigned char)request.data[i]));
        reply->data[i] = request.data[i] + 1;
    }
    printf("\", sending each byte + 1\n");*/

    if (request.data[0] == 99) {
        quit = true;
    }
}

/*void reg_write_callback(
    syndesi::REGISTER_WRITE_16_request& request,
    syndesi::REGISTER_WRITE_16_reply* reply) {
    cout << "REGISTER_WRITE_16_request_callback" << endl;
    cout << "    address = " << request.address << endl;
    cout << "    data = " << request.data << endl;
    cout << "    reply value : ok" << endl;
    reply->status = REGISTER_WRITE_16_reply::OK;
}*/



int main(int argc, char const* argv[]) {
    (void)argc;
    (void)argv;
    cout << "Syndesi comtest example : device" << endl;
    cout << "Sébastien Deriaz    20.08.2022" << endl;

    core.init();

    RawInterpreter raw(raw_callback, nullptr);
    core.frameManager << raw;

    cout << "Listening for commands on port " << syndesi::settings.getIPPort() << " ..." << endl;

    while (!quit) {
        ethernetController.wait_for_connection();
    }

    return 0;
}

