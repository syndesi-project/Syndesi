#!/bin/sh
cd arduino
rm -r syndesi syndesi.zip
mkdir syndesi
mkdir syndesi/examples

touch syndesi/keywords.txt

touch syndesi/examples/test.ino


cp ../include/*.h syndesi -f
cp ../src/*.cpp syndesi -f

# Copy examples
cp ../arduino_examples/* examples -r -f

zip -r syndesi.zip syndesi -q
