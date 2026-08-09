#include <WiFi.h>
#include <Firebase_ESP_Client.h>
#include <addons/TokenHelper.h>
#include <addons/RTDBHelper.h>
#include <Keypad.h>
#include <Wire.h>
#include <BH1750.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
#include <ESP32Servo.h>
#include <Preferences.h>
#include <esp_task_wdt.h>

// ================= CẤU HÌNH MẠNG & FIREBASE =================
#define WIFI_SSID "wifi_ssid"
#define WIFI_PASSWORD "wifi_password"
#define API_KEY "api_key"
#define DATABASE_URL "firebase_database_url"

FirebaseData streamData;
FirebaseData pushData;
FirebaseAuth auth;
FirebaseConfig config;
bool isFirebaseConnected = false;

// ================= ĐỊNH NGHĨA CHÂN =================
#define RX2_PIN 16
#define TX2_PIN 17
#define PIR_PIN 35
#define MC38_PIN 32
#define BUZZER_PIN 4
#define RELAY_NGOAI 5
#define RELAY_TRONG 15
#define SERVO1_PIN 18  
#define SERVO2_PIN 19  

Servo servo1;
Servo servo2;
Preferences preferences; 

// ================= CẤU HÌNH BÀN PHÍM =================
const byte ROWS = 4;
const byte COLS = 3;
char keys[ROWS][COLS] = {
  {'1','2','3'},
  {'4','5','6'},
  {'7','8','9'},
  {'*','0','#'}
};
byte rowPins[ROWS] = {13, 12, 14, 27};
byte colPins[COLS] = {26, 25, 33};
Keypad keypad = Keypad(makeKeymap(keys), rowPins, colPins, ROWS, COLS);

BH1750 lightMeter;

enum SystemState { SYS_IDLE, WAIT_PASSWORD, DOOR_OPEN };
SystemState currentState = SYS_IDLE;

String inputPassword = "";
String correctPassword = ""; 
unsigned long lightOutsideTimer = 0;
unsigned long lightInsideTimer = 0;
unsigned long authTimer = 0;
unsigned long doorOpenTimer = 0;
unsigned long lastUartSync = 0;

bool isOutsideLightOn = false;
bool isInsideLightOn = false;
bool isDoorPhysicallyOpen = false;
bool isRotate = false; 
bool isPending = false;

// ================= HÀM ĐIỀU KHIỂN CÒI =================
void beep(int times, int duration_ms) {
  for (int i = 0; i < times; i++) {
    esp_task_wdt_reset(); 
    digitalWrite(BUZZER_PIN, HIGH);
    vTaskDelay(pdMS_TO_TICKS(duration_ms));
    digitalWrite(BUZZER_PIN, LOW);
    if (i < times - 1) vTaskDelay(pdMS_TO_TICKS(duration_ms));
  }
}

// ================= HÀM CẬP NHẬT TRẠNG THÁI THỰC LÊN FIREBASE =================
void pushStatus(const String &path, const String &value) {
  if (!isFirebaseConnected) return;
  
  if (Firebase.RTDB.setString(&pushData, path, value)) {
    Serial.printf("[FIREBASE] Da cap nhat trang thai: %s = %s\n", path.c_str(), value.c_str());
  } else {
    Serial.printf("[FIREBASE] LOI cap nhat %s: %s\n", path.c_str(), pushData.errorReason().c_str());
    pushData.clear();
  }
}

// ================= HÀM XỬ LÝ LỆNH FIREBASE =================
void streamCallback(FirebaseStream data) {
  String path = data.dataPath(); 
  String type = data.dataType();
  
  Serial.printf("\n[STREAM EVENT] Path: %s | Type: %s\n", path.c_str(), type.c_str());
  
  String value = "";

  if (type == "json" || type == "JSON") {
    FirebaseJson json;
    json.setJsonData(data.payload()); 
    FirebaseJsonData result;
    if (json.get(result, "value")) {
      value = result.stringValue;
    }
  } 
  else if (type == "string") {
    value = data.stringData();
  }

  if (value == "") return;

  Serial.println("-> VALUE DOC DUOC: " + value);

if (path.indexOf("/ai_status") != -1) {
    if (value == "pending") {
      Serial.println("[FIREBASE] AI PENDING -> Keu 1 bip");
      isPending = true; // <-- BẬT CỜ: Đang chờ Web xử lý
      beep(1, 100); 
    }
    else if (value == "known" && currentState == SYS_IDLE) {
      Serial.println("[FIREBASE] AI KNOWN -> Nguoi quen, Mo Servo 1");
      isPending = false; // <-- TẮT CỜ: Đã xử lý xong
      isRotate = true;
      beep(1, 100);      
      servo1.write(180);
      currentState = WAIT_PASSWORD;
      authTimer = millis(); 
      inputPassword = ""; 
    }
    else if (value == "unknown") {
      Serial.println("[FIREBASE] AI UNKNOWN -> Canh bao");
      isPending = false; // <-- TẮT CỜ: Đã xử lý xong
      beep(5, 200); 
    }
    else if (value == "idle") {
      Serial.println("[FIREBASE] AI IDLE -> Ket thuc phan tich");
      isPending = false; // <-- TẮT CỜ
    }
  }
  
  else if (path.indexOf("/door") != -1) {
    if (value == "open") {
      Serial.println("[FIREBASE] Mo cua tu xa!");
      isRotate = true;
      servo1.write(180);
      servo2.write(180); 
      beep(1, 600);     
      currentState = DOOR_OPEN;
      pushStatus("/device_status/lock", "unlocked"); 
    }
    else if (value == "close") {
      Serial.println("[FIREBASE] Khoa cua tu xa!");
      isRotate = false;
      servo2.write(0);
      servo1.write(90);
      currentState = SYS_IDLE; 
      pushStatus("/device_status/lock", "locked"); 
    }
  }
  else if (path.indexOf("/light") != -1) {
    if (value == "on") {
      isInsideLightOn = true;
      digitalWrite(RELAY_TRONG, HIGH);
      lightInsideTimer = millis();
      preferences.putBool("light_on", true); 
      Serial.println("[FIREBASE] Bat den trong");
      pushStatus("/device_status/light_inside", "on"); 
    }
    else if (value == "off") {
      isInsideLightOn = false;
      digitalWrite(RELAY_TRONG, LOW);
      preferences.putBool("light_on", false); 
      Serial.println("[FIREBASE] Tat den trong");
      pushStatus("/device_status/light_inside", "off"); 
    }
  }
  else if (path.indexOf("/pass_keypad") != -1) {
    correctPassword = value; 
    preferences.putString("password", correctPassword); 
    Serial.print("[FIREBASE] DA DOI MAT KHAU SANG: ");
    Serial.println(correctPassword);
    beep(3, 100); 
  }
}

void streamTimeoutCallback(bool timeout) {
  if (timeout) {
    Serial.println("[FIREBASE] Stream timeout -> Ket noi lai...");
  }
}

void setup() {
  Serial.begin(115200);
  Serial2.begin(115200, SERIAL_8N1, RX2_PIN, TX2_PIN); 

  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.print("Dang ket noi WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    Serial.print(".");
    delay(500);
  }
  Serial.println("\nWiFi da ket noi!");
  WiFi.setSleep(false);

  config.api_key = API_KEY;
  config.database_url = DATABASE_URL;

  if (Firebase.signUp(&config, &auth, "", "")) {
    Serial.println("Firebase Auth thanh cong");
    isFirebaseConnected = true;
  }
  Firebase.begin(&config, &auth);
  Firebase.reconnectWiFi(true);
  
  Serial.print("Dang xac thuc Token voi Google...");
  while (!Firebase.ready()) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\n[FIREBASE] Xac thuc thanh cong!");

  if (!Firebase.RTDB.beginStream(&streamData, "/device_control")) {
    Serial.printf("Loi Stream: %s\n", streamData.errorReason().c_str());
  } else {
    Firebase.RTDB.setStreamCallback(&streamData, streamCallback, streamTimeoutCallback);
    Serial.println("[FIREBASE] Stream ket noi hoan hao!");
  }
  
  preferences.begin("door_sys", false); 
  correctPassword = preferences.getString("password", "123"); 
  
  servo1.setPeriodHertz(50);
  servo2.setPeriodHertz(50);
  servo1.attach(SERVO1_PIN, 500, 2400);
  servo2.attach(SERVO2_PIN, 500, 2400);
  
  pinMode(PIR_PIN, INPUT);
  pinMode(MC38_PIN, INPUT_PULLUP);
  pinMode(BUZZER_PIN, OUTPUT);
  pinMode(RELAY_NGOAI, OUTPUT);
  pinMode(RELAY_TRONG, OUTPUT);
  
  digitalWrite(RELAY_NGOAI, LOW); 
  digitalWrite(RELAY_TRONG, LOW);

  Wire.begin(21, 22);
  if (lightMeter.begin()) {
    Serial.println("BH1750 khoi tao thanh cong!");
  }

  isDoorPhysicallyOpen = (digitalRead(MC38_PIN) == HIGH);
  if (isDoorPhysicallyOpen) {
    isRotate = true;
    servo1.write(180);
    servo2.write(180);
    currentState = DOOR_OPEN;
    Serial.println("[REBOOT RECOVERY] Cua dang mo -> Mo 2 Servo.");
  } else {
    isRotate = false;
    servo1.write(90);
    servo2.write(0);
    currentState = SYS_IDLE;
    Serial.println("[REBOOT RECOVERY] Cua dang dong -> Khoa 2 Servo.");
  }

  if (preferences.getBool("pending_alert", false)) {
    Serial.println("[REBOOT RECOVERY] Phat hien co thong bao bi lo! Dang gui bu...");
    if (Firebase.RTDB.setBool(&pushData, "/device_control/door_alert", true)) {
      preferences.putBool("pending_alert", false); 
      Serial.println("[REBOOT RECOVERY] Da gui bu SOS door_alert thanh cong!");
    }
  }

  if (preferences.getBool("light_on", false)) {
    isInsideLightOn = true;
    digitalWrite(RELAY_TRONG, HIGH);
    lightInsideTimer = millis(); 
    Serial.println("[REBOOT RECOVERY] Phat hien den trong dang sang -> Bat lai den!");
  }

  pushStatus("/device_status/lock", isDoorPhysicallyOpen ? "unlocked" : "locked");
  pushStatus("/device_status/light_inside", isInsideLightOn ? "on" : "off");

  esp_task_wdt_config_t twdt_config = {
      .timeout_ms = 2000,                              
      .idle_core_mask = (1 << portNUM_PROCESSORS) - 1, 
      .trigger_panic = true                            
  };
  esp_task_wdt_init(&twdt_config); 
  esp_task_wdt_add(NULL);
  
  Serial.println("He thong trung tam da san sang!");
}

void loop() {
  esp_task_wdt_reset(); 

  unsigned long currentMillis = millis();

  if (currentMillis - lastUartSync >= 1000) { // 1s mới gửi để hàm thằng detect bên esp32-cam thoải mái quét hơn thay vì 0.5s
    lastUartSync = currentMillis;
    Serial2.print("DOOR:");
    Serial2.print(isDoorPhysicallyOpen ? "1" : "0");
    Serial2.print(",PEND:");
    // CAM sẽ KHÔNG ĐƯỢC CHỤP nếu Servo 1 đang mở HOẶC Web đang bận phân tích
    Serial2.println((isRotate || isPending) ? "1" : "0");
  }

  if (Serial.available()) {
    char debugCmd = Serial.read();
    if (debugCmd == '1' && currentState == SYS_IDLE) {
      isRotate = true; 
      beep(1, 100);      
      servo1.write(180);
      currentState = WAIT_PASSWORD;
      authTimer = currentMillis; 
      inputPassword = ""; 
    }
    else if (debugCmd == '2') {
      beep(5, 200); 
    }
  }

  int pirState = digitalRead(PIR_PIN);
  if (pirState == HIGH && !isOutsideLightOn) {
    float lux = lightMeter.readLightLevel();
    if (lux >= 0 && lux < 20) { 
      digitalWrite(RELAY_NGOAI, HIGH);
      isOutsideLightOn = true;
      lightOutsideTimer = currentMillis;
    }
  }
  
  if (isOutsideLightOn && (currentMillis - lightOutsideTimer >= 20000)) {
    digitalWrite(RELAY_NGOAI, LOW);
    isOutsideLightOn = false;
  }

  if (isInsideLightOn && (currentMillis - lightInsideTimer >= 300000)) { 
    digitalWrite(RELAY_TRONG, LOW);
    isInsideLightOn = false;
    preferences.putBool("light_on", false); 
    Serial.println("[Timer] Het 5 phut -> Tat den trong.");
    pushStatus("/device_status/light_inside", "off"); 
  }

  if (currentState == WAIT_PASSWORD) {
    char key = keypad.getKey();
    
    if (currentMillis - authTimer >= 30000) {
      servo1.write(90);
      isRotate = false;
      beep(3, 300); 
      currentState = SYS_IDLE;
      inputPassword = "";
    }
    
    if (key) {
      if (key == '#') { 
        if (inputPassword == correctPassword) {
          Serial.println("[PASS] Mat khau DUNG! -> Mo Servo 2, Bat den trong.");
          servo2.write(180);
          beep(2, 800); 
          digitalWrite(RELAY_TRONG, HIGH);
          isInsideLightOn = true;
          lightInsideTimer = currentMillis;
          preferences.putBool("light_on", true); 
          
          currentState = DOOR_OPEN;
          pushStatus("/device_status/lock", "unlocked");       
          pushStatus("/device_status/light_inside", "on");     
        } else {
          inputPassword = ""; 
        }
      } 
      else if (key == '*') { 
        inputPassword = "";
      } 
      else {
        inputPassword += key;
      }
    }
  }

  int doorState = digitalRead(MC38_PIN);
  
  if (doorState == HIGH) { 
    if (!isDoorPhysicallyOpen) {
      isDoorPhysicallyOpen = true;
      doorOpenTimer = currentMillis; 
      Serial.println("[MC-38] Cua vat ly VUA MO ra.");
      if (isInsideLightOn) lightInsideTimer = currentMillis; 
    }
    
    if (currentMillis - doorOpenTimer >= 180000) { 
       Serial.println("[CANH BAO] Cua mo qua 180s! Phat canh bao Telegram.");
       beep(3, 100); 
       
       if (isFirebaseConnected) {
           preferences.putBool("pending_alert", true); 

           if (Firebase.RTDB.setBool(&pushData, "/device_control/door_alert", true)) {
             preferences.putBool("pending_alert", false); 
             Serial.println("[FIREBASE] Da gui SOS door_alert thanh cong");
           } else {
             Serial.printf("[FIREBASE] LOI gui SOS door_alert: %s\n", pushData.errorReason().c_str());
             pushData.clear();
           }
       }
       doorOpenTimer = currentMillis; 
    }
  } 
  else { 
    if (isDoorPhysicallyOpen) {
      isDoorPhysicallyOpen = false;
      Serial.println("[MC-38] Cua vat ly DA DONG. -> Khoa cung 2 Servo.");
      isRotate = false;
      servo2.write(0);
      servo1.write(90);
      currentState = SYS_IDLE; 
      pushStatus("/device_status/lock", "locked");  
    }
  }

  vTaskDelay(pdMS_TO_TICKS(10)); 
}