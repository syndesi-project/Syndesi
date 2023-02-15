#!/bin/sh

./make_arduino_library.sh

rm -rf ~/Arduino/libraries/syndesi

cp -r arduino/syndesi ~/Arduino/libraries
