#include <SPI.h>
#include <MFRC522.h>
#include <Wire.h>
#include <LiquidCrystal_I2C.h>

#define RST_PIN  9
#define SS_PIN   10

MFRC522 rfid(SS_PIN, RST_PIN);
LiquidCrystal_I2C lcd(0x27, 16, 2);

byte normalUID[]  = {0x63, 0xCE, 0xFA, 0x03};
byte specialUID[] = {0x33, 0x83, 0xF0, 0x2C};

unsigned long lastRead  = 0;
const unsigned long DEBOUNCE_MS = 2000;

// ─────────────────────────────────────────────
bool matchUID(byte *uid, byte *target) {
  for (int i = 0; i < 4; i++)
    if (uid[i] != target[i]) return false;
  return true;
}

void lcdLine(int row, String text) {
  // pad / truncate to exactly 16 chars
  while (text.length() < 16) text += " ";
  text = text.substring(0, 16);
  lcd.setCursor(0, row);
  lcd.print(text);
}

void showIdle() {
  lcdLine(0, "Bus Running...  ");
  lcdLine(1, "Tap card 2 Pay  ");
}

// ─────────────────────────────────────────────
void setup() {
  Serial.begin(9600);
  SPI.begin();
  rfid.PCD_Init();

  Wire.begin();
  delay(100);
  lcd.init();
  delay(50);
  lcd.init();       // double init fixes clone LCD garbled chars
  delay(50);
  lcd.backlight();
  lcd.clear();
  delay(200);

  // RC522 self-test
  byte v = rfid.PCD_ReadRegister(MFRC522::VersionReg);
  if (v == 0x00 || v == 0xFF) {
    lcd.clear();
    lcdLine(0, "RC522 ERROR!    ");
    lcdLine(1, "Check wiring    ");
    Serial.println("ERROR:RC522");
    while (true);
  }

  Serial.print("RC522 v0x");
  Serial.println(v, HEX);   // 0x91 = v1, 0x92 = v2

  lcd.clear();
  lcdLine(0, "  Bus Fare Sys  ");
  lcdLine(1, "  Ring Road...  ");
  delay(1500);

  showIdle();
  Serial.println("READY");
}

// ─────────────────────────────────────────────
void loop() {

  // ── messages from Python ─────────────────────────────────────
  if (Serial.available()) {
    String msg = Serial.readStringUntil('\n');
    msg.trim();

    // ── Protocol ─────────────────────────────────────────────
    // L1:<text>   → write text to LCD row 0
    // L2:<text>   → write text to LCD row 1
    // OK:<text>   → Payment success  (show 2.5s then idle)
    // FAIL        → Low balance      (show 2s   then idle)
    // NOFFARE     → Bus not started  (show 1.5s then idle)

    if (msg.startsWith("L1:")) {
      lcdLine(0, msg.substring(3));

    } else if (msg.startsWith("L2:")) {
      lcdLine(1, msg.substring(3));

    } else if (msg.startsWith("OK:")) {
      String info = msg.substring(3);
      lcd.clear();
      lcdLine(0, "Payment OK!     ");
      lcdLine(1, info);
      delay(2500);
      showIdle();

    } else if (msg == "FAIL") {
      lcd.clear();
      lcdLine(0, " LOW BALANCE!   ");
      lcdLine(1, " Recharge card  ");
      delay(2000);
      showIdle();

    } else if (msg == "NOFFARE") {
      lcd.clear();
      lcdLine(0, "No fare yet!    ");
      lcdLine(1, "Start the bus   ");
      delay(1500);
      showIdle();
    }
  }

  // ── card scan ─────────────────────────────────────────────────
  if (!rfid.PICC_IsNewCardPresent() || !rfid.PICC_ReadCardSerial()) return;

  // debounce
  if (millis() - lastRead < DEBOUNCE_MS) {
    rfid.PICC_HaltA();
    rfid.PCD_StopCrypto1();
    return;
  }
  lastRead = millis();

  lcd.clear();

  if (matchUID(rfid.uid.uidByte, normalUID)) {
    lcdLine(0, "Normal Card     ");
    lcdLine(1, "Processing...   ");
    Serial.println("NORMAL");         // Python processes the fare

  } else if (matchUID(rfid.uid.uidByte, specialUID)) {
    lcdLine(0, "Student/Senior  ");
    lcdLine(1, "Processing...   ");
    Serial.println("SPECIAL");        // Python processes the fare

  } else {
    // print full UID so you can register new cards
    Serial.print("UNKNOWN:");
    for (byte i = 0; i < rfid.uid.size; i++) {
      if (rfid.uid.uidByte[i] < 0x10) Serial.print("0");
      Serial.print(rfid.uid.uidByte[i], HEX);
      if (i < rfid.uid.size - 1) Serial.print(":");
    }
    Serial.println();

    lcdLine(0, "Unknown Card!   ");
    lcdLine(1, "Not registered  ");
    delay(1500);
    showIdle();
  }

  rfid.PICC_HaltA();
  rfid.PCD_StopCrypto1();
}
