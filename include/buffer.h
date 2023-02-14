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
    bool isparent = true;
    size_t _offset = 0;
    size_t _clipLength = 0;

   public:
    /**
     * @brief Construct a new empty Buffer object with size length
     *
     * @param length
     */
    Buffer(){};
    Buffer(size_t length) { 
        allocate(length);
        };
    ~Buffer() { deallocate(); };
    Buffer(Buffer* parent, size_t offset, size_t length = 0) {
        fromParent(parent, offset, length);
    }
    Buffer(char* buffer, size_t length) { fromBuffer(buffer, length); };

    /**
     * @brief Copy assignement
     *
     * @param other
     * @return Buffer&
     */
    Buffer& operator=(const Buffer& other);

    /**
     * @brief Canonical move
     *
     * @param other
     * @return Buffer&
     */
    char& operator[](size_t i) { return data()[i]; }

   private:
   public:
    void allocate(size_t length);

    void deallocate();

    /**
     * @brief Create a subbuffer (with an offset compared to the first one)
     *
     * @param parent the parent buffer
     * @param offset the start offset of the data
     */
    void fromParent(const Buffer* parent, size_t offset, size_t length = 0);

    /**
     * @brief Init with the given buffer
     *
     * @param buffer
     * @param length
     */
    void fromBuffer(char* buffer, size_t length);

    /**
     * @brief Create a sub-buffer
     *
     * @param offset offset from start
     * @param length length of sub-buffer (default to max)
     */
    //Buffer& offset(size_t offset, size_t length = 0);

    size_t length() const;

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

    void dump(char* dest, size_t maxLength) {
        memcpy(dest, data(), std::min(length(), maxLength));
    }

#ifdef ENABLE_PRINTING
    void print() {
        const unsigned char* start = reinterpret_cast<unsigned char*>(data());
        for (size_t i = 0; i < length(); i++) {
            printf("%02X ", (unsigned int)(start[i]));
        }
    }
#endif  // ENABLE_PRINTING
};
}  // namespace syndesi

#endif  // BUFFER_H
