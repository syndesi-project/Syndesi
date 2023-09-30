void setup() {
  Serial.begin(115200);
}

char c;
#define KEYCHAR 'x'

void loop() {
  if (Serial.available() > 0) {
    c = Serial.read();
    if (c == KEYCHAR) {
      // Start the sequence
      delay(250);
      Serial.print("ABCDE");
      delay(100);
      Serial.print("FGHIJ");
      delay(500);
      Serial.print("KLMNO");
      delay(1000);
      Serial.print("PQRST");
      delay(1000);
      Serial.print("UVWXYZ");
    }
  }
}