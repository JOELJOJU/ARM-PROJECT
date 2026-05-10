#include <Wire.h>
#include <Adafruit_PWMServoDriver.h>

Adafruit_PWMServoDriver pwm = Adafruit_PWMServoDriver();

#define SERVOMIN  150  // Minimum pulse length count (out of 4096)
#define SERVOMAX  600  // Maximum pulse length count (out of 4096)

int servo_channels[4] = {0, 1, 2, 3};
int servo_angles[4] = {40, 90, 0, 150};  // Initial angles

void setup() {
  Serial.begin(19200);  // Match baud rate with Python script
  pwm.begin();
  pwm.setPWMFreq(60);  // Analog servos run at ~60 Hz

  // Set initial servo positions one by one
  for (int i = 0; i < 4; i++) {
    setServoAngle(servo_channels[i], servo_angles[i]);
    delay(500);
  }
}

void loop() {
  if (Serial.available()) {
    String data = Serial.readStringUntil('\n');
    data.trim();
    if (data.length() > 0) {
      parseAngles(data);

      // Update servos
      for (int i = 0; i < 4; i++) {
        setServoAngle(servo_channels[i], servo_angles[i]);
      }
    }
  }
}

void setServoAngle(int channel, int angle) {
  int pulse = map(angle, 0, 180, SERVOMIN, SERVOMAX);
  pwm.setPWM(channel, 0, pulse);
}

void parseAngles(String data) {
  int index = 0;
  int start = 0;
  data += ',';  // Ensure the last value is read
  for (int i = 0; i < data.length(); i++) {
    if (data.charAt(i) == ',') {
      String value = data.substring(start, i);
      servo_angles[index] = value.toInt();
      index++;
      start = i + 1;
      if (index >= 4) break;
    }
  }
}
