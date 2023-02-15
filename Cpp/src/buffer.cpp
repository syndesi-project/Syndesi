/**
 * @file buffer.cpp
 *
 * @brief General purpose buffer
 *
 * @author Sébastien Deriaz
 * @date 16.08.2022
 */

#include "buffer.h"

namespace syndesi {

Buffer& Buffer::operator=(const Buffer& other) {
    allocate(other.length());
    if (data()) {
        memcpy(data(), other.data(), other.length());
    }
    return *this;
}

void Buffer::allocate(size_t length) {
    deallocate();  // Deallocate if there was a previous buffer
    _data = (char*)malloc(length);
    if (_data != nullptr) {
        // Ok
        _length = length;
    } else {
        printf("Couldn't allocate buffer");
        _length = 0;
    }
    _offset = 0;
    _clipLength = _length;
    isparent = true;
};

void Buffer::deallocate() {
    // free the data if
    // - there's something to free
    // - it's not externally owned
    if (_data != nullptr && isparent) {
        free(_data);
        _data = nullptr;
    }
};

void Buffer::fromParent(const Buffer* parent, size_t offset, size_t length) {
    isparent = false;
    if (offset > parent->length()) {
        // Cannot create a sub-buffer with offset greater than the parent's
        // length
    } else {
        _data = parent->_data;
        _offset = offset;
        _clipLength = length;
        _length = parent->length();
    }
}

void Buffer::fromBuffer(char* buffer, size_t length) {
    // Allocate a new buffer
    // Copy the data locally
    allocate(length);
    if (_data != nullptr) {
        memcpy(_data, buffer, length);
        _length = length;
    }
    isparent = true;
}

/*Buffer& Buffer::offset(size_t offset, size_t length) {
    Buffer buf;
    buf.fromParent(this, offset, length);
    return buf;
}*/

size_t Buffer::length() const {
    // Set the max length
    if (_offset > _length) {
        return 0;
    }
    size_t len = _length - _offset;

    // If a clip is defined and it is valid, use it
    if (_clipLength < len) {
        len = _clipLength;
    }
    return len;
};

}  // namespace syndesi