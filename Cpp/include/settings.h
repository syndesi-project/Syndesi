/**
 * @file settings.h
 *
 * @brief Syndesi settings
 *
 * @author Sébastien Deriaz
 * @date 02.11.2022
 */

#ifndef SETTINGS_H
#define SETTINGS_H

namespace syndesi {
    
class Settings {
   private:
    const unsigned short default_syndesi_port = 2608;
    unsigned short IPPort = default_syndesi_port;

   public:
    unsigned short getIPPort() {return IPPort;}
    void setIPPort(unsigned short port) {IPPort = port;}
};

extern Settings settings;

}

#endif  // SETTINGS_H