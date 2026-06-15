/*
  ╔══════════════════════════════════════════════════════╗
  ║     RFID Bus Fare Management System                  ║
  ║     Card UID  : 63 CE FA 03  → Normal fare (100%)   ║
  ║     Tag UID   : 33 83 F0 2C  → Special fare (55%)   ║
  ╚══════════════════════════════════════════════════════╝

  Connections:
    RC522  → SDA=10, SCK=13, MOSI=11, MISO=12, RST=9, 3.3V, GND
    LCD    → I2C module: SDA=A4, SCL=A5, VCC=5V, GND
    GREEN LED → Pin 4 (with 220Ω resistor)
    RED LED   → Pin 5 (with 220Ω resistor)
    BUZZER    → Pin 7
*/

#include <SPI.h>
#include <MFRC522.h>
#include <Wire.h>
#include <LiquidCrystal_I2C.h>

#define RST_PIN  9
#define SS_PIN   10
#define GREEN    4
#define RED      5
#define BUZZER   7

MFRC522 rfid(SS_PIN, RST_PIN);
LiquidCrystal_I2C lcd(0x27, 16, 2);  // try 0x3F if LCD stays blank

//  CARD UIDs -----
byte normalUID[]  = {0x63, 0xCE, 0xFA, 0x03};  // White card  → Normal (100%)
byte specialUID[] = {0x33, 0x83, 0xF0, 0x2C};  // Key tag     → Special (55%)

// ───────────────────────────────────────────────────────
void setup() {
  Serial.begin(9600);
  SPI.begin();
  rfid.PCD_Init();
  Wire.begin();
  lcd.begin(16, 2);
  lcd.backlight();

  pinMode(GREEN,  OUTPUT);
  pinMode(RED,    OUTPUT);
  pinMode(BUZZER, OUTPUT);

  // Check RC522 is wired correctly
  byte version = rfid.PCD_ReadRegister(MFRC522::VersionReg);
  if (version == 0x00 || version == 0xFF) {
    lcd.setCursor(0, 0); lcd.print("RC522 ERROR!    ");
    lcd.setCursor(0, 1); lcd.print("Check wiring    ");
    while (true);  // halt
  }

  // Startup message
  lcd.setCursor(0, 0); lcd.print("  Bus Fare Sys  ");
  lcd.setCursor(0, 1); lcd.print("  Starting...   ");
  delay(1500);
  lcd.clear();
  lcd.setCursor(0, 0); lcd.print("Bus Running...  ");
  lcd.setCursor(0, 1); lcd.print("Tap card 2 Pay  ");

  Serial.println("READY");
}

// ───────────────────────────────────────────────────────
void loop() {

  // ── Listen for result FROM Python ──────────────────
  if (Serial.available()) {
    String msg = Serial.readStringUntil('\n');
    msg.trim();

    lcd.clear();

    if (msg.startsWith("OK")) {
      // Format received: "OK:Rs.12.50"
      String amount = msg.substring(3);   // "Rs.12.50"
      lcd.setCursor(0, 0); lcd.print("Payment Success!");
      lcd.setCursor(0, 1); lcd.print(amount);
      digitalWrite(GREEN, HIGH);
      tone(BUZZER, 1200, 200);
      delay(100);
      tone(BUZZER, 1500, 200);
      delay(2000);
      digitalWrite(GREEN, LOW);
    }
    else if (msg == "FAIL") {
      lcd.setCursor(0, 0); lcd.print(" LOW BALANCE!   ");
      lcd.setCursor(0, 1); lcd.print(" Recharge card  ");
      for (int i = 0; i < 3; i++) {
        digitalWrite(RED, HIGH);
        tone(BUZZER, 400, 120);
        delay(250);
        digitalWrite(RED, LOW);
        delay(200);
      }
    }
    else if (msg == "UNKNOWN") {
      lcd.setCursor(0, 0); lcd.print("Unknown Card!   ");
      lcd.setCursor(0, 1); lcd.print("Not registered  ");
      tone(BUZZER, 300, 500);
      delay(1500);
    }
    else if (msg == "NOFFARE") {
      lcd.setCursor(0, 0); lcd.print("No fare yet!    ");
      lcd.setCursor(0, 1); lcd.print("Wait for bus... ");
      tone(BUZZER, 600, 200);
      delay(1500);
    }

    // Reset display
    lcd.clear();
    lcd.setCursor(0, 0); lcd.print("Bus Running...  ");
    lcd.setCursor(0, 1); lcd.print("Tap card 2 Pay  ");
  }

  // ── Read RFID card / tag ────────────────────────────
  if (!rfid.PICC_IsNewCardPresent() || !rfid.PICC_ReadCardSerial()) return;

  lcd.clear();

  if (matchUID(rfid.uid.uidByte, normalUID)) {
    lcd.setCursor(0, 0); lcd.print("Normal Card     ");
    lcd.setCursor(0, 1); lcd.print("Processing...   ");
    Serial.println("NORMAL");
  }
  else if (matchUID(rfid.uid.uidByte, specialUID)) {
    lcd.setCursor(0, 0); lcd.print("Student/Senior  ");
    lcd.setCursor(0, 1); lcd.print("Processing...   ");
    Serial.println("SPECIAL");
  }
  else {
    lcd.setCursor(0, 0); lcd.print("Unknown Card!   ");
    lcd.setCursor(0, 1); lcd.print("Not registered  ");
    Serial.println("UNKNOWN");
    tone(BUZZER, 300, 500);
    delay(1500);
    lcd.clear();
    lcd.setCursor(0, 0); lcd.print("Bus Running...  ");
    lcd.setCursor(0, 1); lcd.print("Tap card 2 Pay  ");
  }

  rfid.PICC_HaltA();
  rfid.PCD_StopCrypto1();
  delay(1000);
}

// ── UID comparison helper ────────────────────────────
bool matchUID(byte *uid, byte *target) {
  for (int i = 0; i < 4; i++)
    if (uid[i] != target[i]) return false;
  return true;
}
