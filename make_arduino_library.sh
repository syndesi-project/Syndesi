#!/bin/sh
cd arduino
rm -r syndesi
mkdir syndesi
mkdir syndesi/include
mkdir syndesi/src
mkdir syndesi/user_config
mkdir syndesi/examples

touch syndesi/keywords.txt

touch syndesi/examples/test.ino


cp ../include/*.h syndesi
cp ../src/*.cpp syndesi
#cp ../user_config/*.h syndesi

# Copy examples
cp ../arduino_examples/* examples -r

zip -r syndesi.zip syndesi -q
