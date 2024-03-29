

/*
 DHCP Chat  Server

 A simple server that distributes any incoming messages to all
 connected clients.  To use, telnet to your device's IP address and type.
 You can see the client's input in the serial monitor as well.
 Using an Arduino Wiznet Ethernet shield.

 THis version attempts to get an IP address using DHCP

 Circuit:
 * Ethernet shield attached to pins 10, 11, 12, 13

 created 21 May 2011
 modified 9 Apr 2012
 by Tom Igoe
 modified 02 Sept 2015
 by Arturo Guadalupi
 Based on ChatServer example by David A. Mellis

 */


#include <SPI.h>
#include <Ethernet.h>

#include <MemoryFree.h>

#include <ArduinoSTL.h>
#include <memory>

#include <syndesi.h>
#include <interpreters/raw.h>

// Enter a MAC address and IP address for your controller below.
// The IP address will be dependent on your local network.
// gateway and subnet are optional:
byte mac[] = {
  0x00, 0xAA, 0xBB, 0xCC, 0xDE, 0x02
};
IPAddress ip(192, 168, 1, 177);
IPAddress myDns(192, 168, 1, 1);
IPAddress gateway(192, 168, 1, 1);
IPAddress subnet(255, 255, 0, 0);


EthernetServer server(2608);

class IPController : public syndesi::SAP::IController {

  EthernetClient client; 
    syndesi::SyndesiID hostID;

   public:

    void init() {
        Ethernet.init(10);  // Most Arduino shields

        Serial.println("Trying to get an IP address using DHCP");
        if (Ethernet.begin(mac) == 0) {
          Serial.println("Failed to configure Ethernet using DHCP");
          // Check for Ethernet hardware present
          if (Ethernet.hardwareStatus() == EthernetNoHardware) {
            Serial.println("Ethernet shield was not found.  Sorry, can't run without hardware. :(");
            while (true) {
              delay(1); // do nothing, no point running without Ethernet hardware
            }
          }
          if (Ethernet.linkStatus() == LinkOFF) {
            Serial.println("Ethernet cable is not connected.");
          }
          // initialize the Ethernet device not using DHCP:
          Ethernet.begin(mac, ip, myDns, gateway, subnet);
        }
        else {
          Serial.println("ok");
        }
        // print your local IP address:
        Serial.print("My IP address: ");
        Serial.println(Ethernet.localIP());
      
        // start listening for clients
        server.begin();
    }

    size_t write(syndesi::SyndesiID& deviceID, char* buffer, size_t length) {
        size_t Nwritten = server.write(buffer, length);

        return Nwritten;
    }

    size_t read(char* _buffer, size_t _length) {
        for(int i = 0;i<_length;i++) {
          _buffer[i] = client.read();
          if (_buffer[i] == -1) {
            return i-1;
          }
          Ethernet.maintain();
        }
        return _length;
    }

    void close() { client.stop(); }

    void wait_for_connection() {
        // wait for a new client:
        do {
        client = server.available();
        } while(!client);
        //Serial.println("client available !");
        
        //hostID.fromIPv4(address.sin_addr.s_addr, address.sin_port);
        dataAvailable(hostID, -1);
        close();
    }
};

IPController controller;
using namespace syndesi;


void raw_callback(RawInterpreter::RawPayloadRequest& request, RawInterpreter::RawPayloadReply& reply) {
    /*reply.data.allocate(request.data.length());
    for(int i = 0;i<request.data.length();i++) {
      reply.data[i] = request.data[i] + 1;
    }*/
    digitalWrite(5, request.data[0] & 0x04);
    digitalWrite(6, request.data[0] & 0x02);
    digitalWrite(7, request.data[0] & 0x01);
}


//RawInterpreter::Callbacks rawCallbacks{.reply = raw_callback};
RawInterpreter raw;
  
void setup() {
  
  // Open serial communications and wait for port to open:
  Serial.begin(115200);
  while (!Serial) {
    ; // wait for serial port to connect. Needed for native USB port only
  }
  Serial.println("ready");

  raw.request = raw_callback;

  syndesi::networkIPController = &controller;
  syndesi::core.frameManager << raw;

  core.init();

  controller.init();

  pinMode(5, OUTPUT);
  pinMode(6, OUTPUT);
  pinMode(7, OUTPUT);
}

void loop() {
  /*Serial.print("freeMemory()=");
  Serial.println(freeMemory());*/
  controller.wait_for_connection();
  //Serial.println("ok");
}
