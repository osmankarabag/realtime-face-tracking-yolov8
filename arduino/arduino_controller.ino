#include <Servo.h>

// Servo motor pin tanımlamaları
#define PAN_SERVO_PIN 9
#define TILT_SERVO_PIN 10

// Servo motor nesneleri
Servo panServo;
Servo tiltServo;

// Servo açı limitleri
const int PAN_MIN = 0;
const int PAN_MAX = 180;
const int TILT_MIN = 0;
const int TILT_MAX = 180;

// Mevcut servo açıları
int currentPan = 90;
int currentTilt = 90;

void setup() {
  // Seri iletişim başlatma
  Serial.begin(9600);
  
  // Servo motorları başlatma
  panServo.attach(PAN_SERVO_PIN);
  tiltServo.attach(TILT_SERVO_PIN);
  
  // Servoları başlangıç pozisyonuna getir
  panServo.write(currentPan);
  tiltServo.write(currentTilt);
}

void loop() {
  if (Serial.available() > 0) {
    // Seri porttan gelen veriyi oku
    String data = Serial.readStringUntil('\n');
    
    // Gelen veriyi parçala (format: "pan,tilt")
    int commaIndex = data.indexOf(',');
    if (commaIndex != -1) {
      int newPan = data.substring(0, commaIndex).toInt();
      int newTilt = data.substring(commaIndex + 1).toInt();
      
      // Açıları sınırlar içinde tut
      newPan = constrain(newPan, PAN_MIN, PAN_MAX);
      newTilt = constrain(newTilt, TILT_MIN, TILT_MAX);
      
      // Servoları hareket ettir
      panServo.write(newPan);
      tiltServo.write(newTilt);
      
      // Mevcut açıları güncelle
      currentPan = newPan;
      currentTilt = newTilt;
    }
  }
} 