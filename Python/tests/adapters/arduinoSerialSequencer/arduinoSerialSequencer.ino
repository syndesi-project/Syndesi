/*
This code acts as a timed response server to test
the timeout system of the Syndesi library
Data to be sent back if formatted as such :
ABCD,100;EFGH,200;IJKL,100;etc...
With the number following a sequence and a "," the delay after which to send the sequence
*/


void setup() {
  Serial.begin(115200);
}

#define BUFFER_SIZE 255
#define DELAY_DELIMITER ','
#define SEQUENCE_DELIMITER ';'
#define MAX_SEQUENCE_SIZE 100
#define MAX_SEQUENCES_COUNT 10

typedef struct Sequence
{
  String data;
  unsigned int delay;
};

Sequence sequences[MAX_SEQUENCES_COUNT];

String buffer;
unsigned char buffer_index = 0;
unsigned long start = 0; 
unsigned char sequences_counter = 0;
char c;

void loop() {
  if (Serial.available() > 0) {
    if (buffer_index == 0) {
      start = millis();
    }
    c = Serial.read();
    if (buffer == DELAY_DELIMITER) {
      // Parse the data so far
      memcpy(sequences[sequences_counter].data, buffer, buffer_index+1);
      sequences[sequences_counter].data[buffer_index+1] = '\0';
    }
    else if (buffer[buffer_index] == SEQUENCE_DELIMITER) {
      // Parse the delay

    }
  }
}