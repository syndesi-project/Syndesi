/**
 * @file buffer.h
 *
 * @brief General purpose buffer
 *
 * @author Sébastien Deriaz
 * @date 16.08.2022
 */

#ifndef BUFFER_H
#define BUFFER_H

#include <stdint.h>
#include <stdlib.h>
#include <string>
#ifndef ARDUINO
#include <memory.h>
#endif


#define ENABLE_PRINTING

#ifdef ENABLE_PRINTING
#include <stdio.h>
#endif

namespace syndesi {

#ifdef ARDUINO
// Use the String class
#define INT_TO_STRING(x) (x)
#else
#define INT_TO_STRING(x) std::to_string(x)
#endif

/**
 * @brief Buffer class
 *
 */

class Buffer {
    char* _data = nullptr;
    size_t _length = 0;
    // Buffer is defined externaly and not managed
    bool external = false;
    bool ownership = false;

   public:
    /**
     * @brief Construct a new empty Buffer object with size length
     *
     * @param length
     */
    Buffer() { _total_offset = 0; };
    Buffer(size_t length) {
        allocate(length);
        _total_offset = 0;
    };
    ~Buffer() { deallocate(); };
    Buffer(Buffer* parent, size_t offset, size_t length = 0) {
        fromParent(parent, offset);
    }
    Buffer(char* buffer, size_t length, bool copy = false, bool ownership = false) {
        fromBuffer(buffer, length, copy, ownership);
    };

    char& operator [](size_t i) {
        return data()[i];
    }

   private:
    size_t _total_offset = 0;
    size_t _offset = 0;
    size_t _clipLength = 0;

   public:
    void allocate(size_t length) {
        deallocate(); // Deallocate if there was a previous buffer
        _data = (char*)malloc(length);
        if (_data != nullptr) {
            // Ok
            _length = length;
        }
        else {
            printf("Couldn't allocate buffer");
            _length = 0;
        }
    };

    void deallocate() {
        // free the data if
        // - there's something to free
        // - it's not externally owned
        if(_data != nullptr && !(external && !ownership)) {
            free(_data);
            _data = nullptr;
        }
    };

    /**
     * @brief Create a subbuffer (with an offset compared to the first one)
     *
     * @param parent the parent buffer
     * @param offset the start offset of the data
     */
    void fromParent(const Buffer* parent, size_t offset, size_t length = 0) {
        external = true;
        ownership = false;
        if (offset > parent->length()) {
            // Cannot create a sub-buffer with offset greater than the parent's
            // length
        }
        _total_offset = parent->_total_offset + offset;
        _data = parent->_data;
        _offset = offset;
        _clipLength = length;
    }

    /**
     * @brief Init with the given buffer
     *
     * @param buffer
     * @param length
     */
    void fromBuffer(char* buffer, size_t length, bool copy, bool ownership) {
        deallocate(); // Deallocate if there was a previous buffer

        // Allocate a new buffer
        if (copy) {
            // Copy the data locally
            allocate(length);
            if(_data != nullptr) {
                memcpy(_data, buffer, length);
                _length = length;
            }
            external = false;
            this->ownership = true; // Override the user value
        }
        else {
            _data = buffer;
            _length = length;
            external = true;
            this->ownership = ownership;
        }
    };

    /**
     * @brief Create a sub-buffer
     *
     * @param offset offset from start
     * @param length length of sub-buffer (default to max)
     */
    Buffer offset(size_t offset, size_t length = 0) {
        Buffer buf;
        buf.fromParent(this, offset, length);
        return buf;
    };

    size_t length() const {
        // Set the max length
        if (_offset > _length) {
            return 0;
        }
        size_t len = _length - _offset;

        // If a clip is defined and it is valid, use it
        if (_clipLength > 0 && _clipLength < len) {
            len = _clipLength;
        }
        return len;
    };

    /**
     * @brief Get the raw data pointer
     *
     */
    char* data() const { return _data + _offset; };

    /**
     * @brief Get the sub-buffer offset (from base buffer)
     *
     * @return size_t
     */
    size_t getOffset() { return _offset; };

    /**
     * @brief Export buffer as string
     *
     */
    char* toString() { return data(); };

    /**
     * @brief Export buffer as hex string (12 F1 8A ...)
     *
     */
    std::string toHex() {
        std::string output;
        /*stringstream output;
        char* start = data();
        for(size_t i = 0;i<length();i++) {
            output << hex << start[i] << " ";
        }
        return output.str();*/
        return output;
    };

#ifdef ENABLE_PRINTING
    void print() {
        const unsigned char* start = reinterpret_cast<unsigned char*>(data());
        for(size_t i = 0;i<length();i++) {
            printf("%02X ", (unsigned int)(start[i]));
        }
    }
#endif // ENABLE_PRINTING
};
}  // namespace syndesi

#endif  // BUFFER_H
