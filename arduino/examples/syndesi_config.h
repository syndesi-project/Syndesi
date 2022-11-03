/* Please edit this file to configure how the syndesi library works
*
* Part of this file has been generated automatically by the script generate_commands.py
* date : 22-11-01 15:11:23
*/


/* ######## General configuration ######### */

/*
* HOST mode : can send commands (a computer for example)
*/
//#define SYNDESI_HOST_MODE

/*
* DEVICE mode : can receive commands (like a I²C interface, SPI interface, etc...)
*/
//#define SYNDESI_DEVICE_MODE

// Both can be activated at the same time to enable HYBRID mode


/* ######## Protocols configuration ####### */

/*
* Configure what controllers are used (uncomment to enable)
*/

// IP Controller
#define USE_IP_CONTROLLER
// Controller MODE
// CONTROLLER_MODE_POLL : Poll for received data
// CONTROLLER_MODE_WAIT : Wait for received data
// CONTROLLER_MODE_IRQ : Interrupt call when data is received
#define IP_CONTROLLER_MODE CONTROLLER_MODE_POLL


// UART Controller
#define USE_UART_CONTROLLER
// Controller MODE
// CONTROLLER_MODE_POLL : Poll for received data
// CONTROLLER_MODE_WAIT : Wait for received data
// CONTROLLER_MODE_IRQ : Interrupt call when data is received
//#define UART_CONTROLLER_MODE

// RS485 Controller
#define USE_RS485_CONTROLLER
// Controller MODE
// CONTROLLER_MODE_POLL : Poll for received data
// CONTROLLER_MODE_WAIT : Wait for received data
// CONTROLLER_MODE_IRQ : Interrupt call when data is received
//#define RS485_CONTROLLER_MODE


/* ######## Callbacks configuration ######## */
/*
*  
* Disabled callback :
* //#define USE_REGISTER_READ_16_REQUEST_CALLBACK
* Enabled callback
* #define USE_REGISTER_READ_16_REQUEST_CALLBACK
*
* The user must then implement it (following the prototype in callbacks.h)
*
* Each request callback follows the format :
*   command_request_callback(request, reply);
* The reply, passed as a pointer, must be editer by the user in the callback
*
* Each reply callback follows the format :
*   command_reply_callback(reply);
* No response to the device will be made
*

*/


/*
* Request callbacks (to be used in device code)
* Only active if DEVICE_MODE is defined
*/
//#define USE_DEVICE_DISCOVER_REQUEST_CALLBACK
//#define USE_REGISTER_READ_16_REQUEST_CALLBACK
//#define USE_REGISTER_WRITE_16_REQUEST_CALLBACK
//#define USE_SPI_READ_WRITE_REQUEST_CALLBACK
//#define USE_SPI_WRITE_ONLY_REQUEST_CALLBACK
//#define USE_I2C_READ_REQUEST_CALLBACK
//#define USE_I2C_WRITE_REQUEST_CALLBACK



/*
* Reply callbacks (to be used in host code)
* Only active if HOST_MODE is defined
*/
//#define USE_ERROR_REPLY_CALLBACK
//#define USE_DEVICE_DISCOVER_REPLY_CALLBACK
//#define USE_REGISTER_READ_16_REPLY_CALLBACK
//#define USE_REGISTER_WRITE_16_REPLY_CALLBACK
//#define USE_SPI_READ_WRITE_REPLY_CALLBACK
//#define USE_SPI_WRITE_ONLY_REPLY_CALLBACK
//#define USE_I2C_READ_REPLY_CALLBACK
//#define USE_I2C_WRITE_REPLY_CALLBACK
