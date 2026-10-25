const int IR_SENSOR_PIN = 2;  // IR Sensor plugged into D2
const int GREEN_LED_PIN = A1; // Green LED on A1 (FALSE = NOT OCCUPIED / Open)
const int BLUE_LED_PIN  = A2; // Blue LED on A2 (TRUE = OCCUPIED / Taken)

// Stability filter for extended IR range (prevents flickering)
const int STABLE_THRESHOLD = 3; 
int consistent_reads = 0;
bool current_occupied = false; 

void setup() {
  Serial.begin(115200);
  
  pinMode(IR_SENSOR_PIN, INPUT);
  pinMode(GREEN_LED_PIN, OUTPUT);
  pinMode(BLUE_LED_PIN, OUTPUT);

  // Initialize state on startup
  // LOW = Red sensor light ON (Object in range -> Occupied -> TRUE)
  current_occupied = (digitalRead(IR_SENSOR_PIN) == LOW);
  updateLEDs(current_occupied);
}

void loop() {
  // Read the IR sensor on D2:
  // LOW  = Red light ON  (Object in range -> TRUE / OCCUPIED)
  // HIGH = Red light OFF (Out of range    -> FALSE / NOT OCCUPIED)
  bool raw_occupied = (digitalRead(IR_SENSOR_PIN) == LOW);

  // Debounce check: require 3 consistent readings before switching LEDs
  if (raw_occupied != current_occupied) {
    consistent_reads++;
    if (consistent_reads >= STABLE_THRESHOLD) {
      current_occupied = raw_occupied;
      consistent_reads = 0;
    }
  } else {
    consistent_reads = 0;
  }

  updateLEDs(current_occupied);
  delay(50); // Check 20 times a second (150ms response time)
}

void updateLEDs(bool is_occupied) {
  if (is_occupied) {
    // TRUE: Object in range (Red sensor light ON) -> Space is OCCUPIED
    digitalWrite(BLUE_LED_PIN, HIGH);  // A2 (Blue) ON
    digitalWrite(GREEN_LED_PIN, LOW);  // A1 (Green) OFF
    Serial.println("occupied: true  -> OCCUPIED (A2 Blue ON, A1 Green OFF)");
  } else {
    // FALSE: Nothing in range (Red sensor light OFF) -> Space is NOT OCCUPIED
    digitalWrite(BLUE_LED_PIN, LOW);   // A2 (Blue) OFF
    digitalWrite(GREEN_LED_PIN, HIGH); // A1 (Green) ON
    Serial.println("occupied: false -> NOT OCCUPIED (A1 Green ON, A2 Blue OFF)");
  }
}