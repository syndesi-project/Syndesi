#!/bin/sh
cd arduino
rm -rf syndesi syndesi.zip
mkdir syndesi
mkdir syndesi/examples

touch syndesi/keywords.txt

touch syndesi/examples/test.ino


cp ../include/* syndesi -rf
cp ../src/* syndesi -rf

# Copy examples
cp ../arduino_examples/* examples -r -f

zip -r syndesi.zip syndesi -q
