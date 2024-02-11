/*
This code acts as a timed response server to test
the timeout system of the Syndesi library
Data to be sent back if formatted as such :
ABCD,100;EFGH,200;IJKL,100;etc...
With the number following a sequence and a "," the delay after which to send the sequence
*/

#define DELAY_DELIMITER ','
#define SEQUENCE_DELIMITER ';'
#define INPUT_DELIMITER '\n'
#define MAX_SEQUENCES_COUNT 5
#define ABSOLUTE_TIME_CORRECTION 0  //positive : increase delay

typedef struct Sequence {
  String data;
  unsigned long delay = 0;
};

unsigned long start = 0;
char sequences_parse_counter = 0;
char sequences_out_counter = 0;
bool delay_nData = false;
unsigned long last_delta = 0;
bool sequence_start = true;

char c;

Sequence sequences[MAX_SEQUENCES_COUNT];

void setup() {
  Serial.begin(115200);

  for (unsigned int i = 0; i < MAX_SEQUENCES_COUNT; i++) {
    sequences[i] = Sequence();
  }
}

void loop() {
  // Serial parser
  if (Serial.available() > 0) {
    if (sequence_start) {
      //start = millis();
      delay_nData = false;
      last_delta = 0;
      sequence_start = false;
    }
    c = Serial.read();
    switch (c) {
      case DELAY_DELIMITER:
        delay_nData = true;
        break;
      case INPUT_DELIMITER:
        sequence_start = true;
        start = millis();
      case SEQUENCE_DELIMITER:
        // Serial.print("Add sequence '");
        // Serial.print(sequences[sequences_parse_counter].data);
        // Serial.print("' after ");
        // Serial.println(sequences[sequences_parse_counter].delay);
        if (sequences[sequences_parse_counter].data.length() > 0) {
          sequences_parse_counter++;
          if (sequences_parse_counter == MAX_SEQUENCES_COUNT) {
            sequences_parse_counter = 0;
          }
        }
        sequences[sequences_parse_counter] = Sequence();
        delay_nData = false;
        break;
      default:
        // Add to the buffer
        if (delay_nData) {
          // Data
          sequences[sequences_parse_counter].delay *= 10;
          sequences[sequences_parse_counter].delay += c - '0';
        } else {
          // Delay
          sequences[sequences_parse_counter].data += c;
        }
        break;
    }
  }


  // Serial writer
  if (sequence_start) {
    if ((sequences_out_counter < sequences_parse_counter && sequences_parse_counter > 0) || (sequences_parse_counter == 0 && sequences_out_counter > 0)) {
      //if ((sequences_out_counter < sequences_parse_counter) ^ (sequences_parse_counter == 0)) {
      if (millis() >= sequences[sequences_out_counter].delay + start + last_delta + ABSOLUTE_TIME_CORRECTION) {
        Serial.print(sequences[sequences_out_counter].data);
        last_delta += sequences[sequences_out_counter].delay;
        sequences_out_counter++;
        if (sequences_out_counter == MAX_SEQUENCES_COUNT) {
          sequences_out_counter = 0;
        }
      }
    }
  }
}
