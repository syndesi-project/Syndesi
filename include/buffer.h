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
    class rawBuffer {
       private:
        char* _data = nullptr;
        size_t _length = 0;
        // Buffer is defined externaly and not managed
        bool external = false;

       public:
        rawBuffer(){};
        rawBuffer(size_t length) {
            _data = (char*)malloc(length);
            if (_data == nullptr) {
                // throw std::bad_alloc();
            } else {
                _length = length;
            }
        };
        ~rawBuffer() {
            if (_data != nullptr && !external) {
                free((char*)_data);
            }
        };
        rawBuffer(char* buffer, size_t length) {
            _data = buffer;
            _length = length;
            external = true;
        };

        char* start() { return _data; };
        size_t length() const { return _length; };
    };

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
    Buffer(char* buffer, size_t length) {
        _data = new rawBuffer(buffer, length);
    };

   private:
    size_t _total_offset = 0;
    size_t _offset = 0;
    rawBuffer* _data = nullptr;
    size_t _clipLength = 0;

   public:
    void allocate(size_t length) {
        if (_data) {
            deallocate();
        }
        _data = new rawBuffer(length);
    };

    void deallocate() { _data = nullptr; };

    /**
     * @brief Create a subbuffer (with an offset compared to the first one)
     *
     * @param parent the parent buffer
     * @param offset the start offset of the data
     */
    void fromParent(const Buffer* parent, size_t offset, size_t length = 0) {
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
    void fromBuffer(char* buffer, size_t length) {
        deallocate();
        _data = new rawBuffer(buffer, length);
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
        size_t len = _data->length() - _offset;
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
    char* data() const { return _data->start() + _offset; };

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
};
}  // namespace syndesi

#endif  // BUFFER_H
