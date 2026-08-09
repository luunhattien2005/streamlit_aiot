#include <Arduino.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include "esp_camera.h"
#include "img_converters.h"
#include "model_data.h"

// Thư viện TensorFlow Lite Micro
#include "tensorflow/lite/micro/micro_mutable_op_resolver.h"
#include "tensorflow/lite/micro/micro_interpreter.h"
#include "tensorflow/lite/schema/schema_generated.h"

// ================= CẤU HÌNH HỆ THỐNG =================
const char* ssid = "wifi_ssid";
const char* password = "wifi_password";

const String imgbb_key = "imgbb_api_key";
const char* firebase_host = "firebase_database_url";

struct ImgBBData {
	String url;
	String delete_url;
	String timestamp;
};

// ================= CHÂN CAMERA AI_THINKER =================
#define PWDN_GPIO_NUM 32
#define RESET_GPIO_NUM -1
#define XCLK_GPIO_NUM 0
#define SIOD_GPIO_NUM 26
#define SIOC_GPIO_NUM 27
#define Y9_GPIO_NUM 35
#define Y8_GPIO_NUM 34
#define Y7_GPIO_NUM 39
#define Y6_GPIO_NUM 36
#define Y5_GPIO_NUM 21
#define Y4_GPIO_NUM 19
#define Y3_GPIO_NUM 18
#define Y2_GPIO_NUM 5
#define VSYNC_GPIO_NUM 25
#define HREF_GPIO_NUM 23
#define PCLK_GPIO_NUM 22

// ================= CẤU HÌNH UART GIAO TIẾP =================
#define RX_ESP_PIN 14
#define TX_ESP_PIN 15
HardwareSerial SerialESP(1);

// Time Checking 
unsigned long lastScanTime = 0;
unsigned long scanInterval = 0;

// Trạng thái lưu trữ từ ESP32 thường
bool isDoorOpen = false;
bool isPending  = false;

// ================= CÁC HÀM HỔ TRỢ ĐỂ GỬI DŨ LIỆU VỀ DATABASE =================
ImgBBData uploadToImgBB(uint8_t* buf, size_t len) {
    ImgBBData data = { "", "", "" };
    WiFiClientSecure client;
    client.setInsecure();

    if (!client.connect("api.imgbb.com", 443)) {
        Serial.println("[ERROR] Fail to connect ImgBB");
        return data;
    }

    String head = "--Boundary\r\nContent-Disposition: form-data; name=\"image\"; filename=\"capture.jpg\"\r\nContent-Type: image/jpeg\r\n\r\n";
    String tail = "\r\n--Boundary--\r\n";
    uint32_t totalLen = head.length() + len + tail.length();

    client.println("POST /1/upload?key=" + imgbb_key + " HTTP/1.1");
    client.println("Host: api.imgbb.com");
    client.println("Content-Length: " + String(totalLen));
    client.println("Content-Type: multipart/form-data; boundary=Boundary");
    client.println();
    client.print(head);
    
    // Gửi mảng byte ảnh JPEG đã cắt hình vuông
    client.write(buf, len);
    client.print(tail);

    String response = "";
    while (client.connected() || client.available()) {
        if (client.available()) {
            response = client.readStringUntil('\n');

            // Bóc tách Link ảnh
            int urlIdx = response.indexOf("\"url\":\"");
            if (urlIdx > 0) {
                int urlEnd = response.indexOf("\"", urlIdx + 7);
                data.url = response.substring(urlIdx + 7, urlEnd);
                data.url.replace("\\/", "/");
            }

            // Bóc tách Link xóa ảnh
            int delIdx = response.indexOf("\"delete_url\":\"");
            if (delIdx > 0) {
                int delEnd = response.indexOf("\"", delIdx + 14);
                data.delete_url = response.substring(delIdx + 14, delEnd);
                data.delete_url.replace("\\/", "/");
            }

            // Bóc tách Timestamp
            int timeIdx = response.indexOf("\"time\":");
            if (timeIdx > 0) {
                int timeEnd = response.indexOf(",", timeIdx + 7);
                data.timestamp = response.substring(timeIdx + 7, timeEnd);
            }

            // Trả về khi đã bóc tách đủ 3 trường
            if (data.url != "" && data.delete_url != "" && data.timestamp != "") {
                client.stop();
                return data;
            }
        }
    }
    client.stop();
    return data;
}

void updateNewRequest(ImgBBData imgData) {
	WiFiClientSecure client;
	client.setInsecure();
	if (!client.connect(firebase_host, 443)) {
		Serial.println("[ERROR] Fail to connect Firebase");
		return;
	}

	// Đóng gói JSON chuẩn 4 trường (chú ý timestamp là số, không dùng ngoặc kép)
	String json = "{\"image_url\":\"" + imgData.url + "\",\"delete_img_url\":\"" + imgData.delete_url + "\",\"timestamp\":" + imgData.timestamp + ",\"status\":\"pending\"}";

	client.println("PUT /new_request/req_" + imgData.timestamp + ".json HTTP/1.1");
	client.println("Host: " + String(firebase_host));
	client.println("Content-Type: application/json");
	client.println("Connection: close");
	client.println("Content-Length: " + String(json.length()));
	client.println();
	client.println(json);

	unsigned long timeout = millis();
	while (client.available() == 0) {
		if (millis() - timeout > 5000) {
			Serial.println("[ERROR] Firebase Timeout");
			client.stop();
			return;
		}
	}

	while (client.available()) {
		client.readStringUntil('\r');
	}

	Serial.println("[DEBUG] Send new_request successfully (include timestamp & delete_url)");
	client.stop();
}

// ================= MÔ HÌNH AI TỰ LÀM =================
const int tensor_arena_size = 1024 * 1024 * 2; 
uint8_t* tensor_arena = NULL;

const tflite::Model* model = nullptr;
tflite::MicroInterpreter* interpreter = nullptr;
TfLiteTensor* input = nullptr;
TfLiteTensor* output = nullptr;
tflite::MicroMutableOpResolver<15> resolver;

void Model_Setup() {
	// Initilize Dummy model
	tensor_arena = (uint8_t*) heap_caps_malloc(tensor_arena_size, MALLOC_CAP_SPIRAM);
	if (tensor_arena == NULL) {
			Serial.println("[ERROR] Fail to allocate PSRAM!");
			while (true);
	}

	// Get model from model_data.h
	model = tflite::GetModel(g_model);
	if (model->version() != TFLITE_SCHEMA_VERSION) {
			Serial.println("[ERROR] Version Schema TFLite is incompatible!");
			while (true);
	}

	// All the layer that is needed for the model
	resolver.AddConv2D();
	resolver.AddDepthwiseConv2D();
	resolver.AddAveragePool2D();
	resolver.AddFullyConnected();
	resolver.AddLogistic();       
	resolver.AddReshape();
	resolver.AddDequantize();
	resolver.AddQuantize();
	resolver.AddMean();
	resolver.AddPad();
	resolver.AddPadV2();

	static tflite::MicroInterpreter static_interpreter(model, resolver, tensor_arena, tensor_arena_size);
	interpreter = &static_interpreter;

	// Check if the model is in ESP32-CAM
	if (interpreter->AllocateTensors() != kTfLiteOk) {
		Serial.println("[ERROR] AllocateTensors() Failed!");
		while (true);
	}

	// Get the input and output of the model (This is global variable so you can call it anywhere)
	input = interpreter->input(0);
  output = interpreter->output(0);
}

float Run_Model_And_Crop(camera_fb_t* fb, uint8_t** cropped_jpg_out, size_t* cropped_jpg_len) {
	int src_w = 800; // Khung ảnh gốc từ SVGA
    int src_h = 600;

	// Time taken
	unsigned long startTime = millis();
	
    // 1. Cấp phát bộ nhớ RAM chứa ảnh RGB888 gốc
    uint8_t *rgb_buffer = (uint8_t *)heap_caps_malloc(src_w * src_h * 3, MALLOC_CAP_SPIRAM);
    if (rgb_buffer == NULL) {
        Serial.println("[ERROR] Not enough PSRAM for High-Res image!\n");
        return 0;
    }

    if (!fmt2rgb888(fb->buf, fb->len, fb->format, rgb_buffer)) {
        Serial.println("[ERROR] Fail to unzip JPEG!\n");
        free(rgb_buffer);
        return 0;
    }

    // 2. Tính toán vị trí khung hình vuông ở CHÍNH GIỮA (600x600)
    int crop_size = 600; 
    int offset_x = (src_w - crop_size) / 2; // = (800 - 600)/2 = 100
    int offset_y = (src_h - crop_size) / 2; // = (600 - 600)/2 = 0

    // 3. TRÍCH XUẤT VÀ RESIZE THẲNG VÀO AI TENSOR (120x120)
    int target_w = 120;
    int target_h = 120;

    for (int y = 0; y < target_h; y++) {
        for (int x = 0; x < target_w; x++) {
            // Tọa độ trên vùng CẮT 600x600
            int crop_x = (x * crop_size) / target_w;
            int crop_y = (y * crop_size) / target_h;

            // Tọa độ thực tế trên mảng RGB gốc 800x600
            int real_x = offset_x + crop_x;
            int real_y = offset_y + crop_y;

            int src_index = (real_y * src_w + real_x) * 3;
            int dst_index = (y * target_w + x) * 3;

            input->data.int8[dst_index + 0] = (int8_t)((int)rgb_buffer[src_index + 0] - 128);
            input->data.int8[dst_index + 1] = (int8_t)((int)rgb_buffer[src_index + 1] - 128);
            input->data.int8[dst_index + 2] = (int8_t)((int)rgb_buffer[src_index + 2] - 128);
        }
    }

    // 4. CHẠY AI SUY LUẬN
    TfLiteStatus invoke_status = interpreter->Invoke();
	unsigned long duration = millis() - startTime;
    int8_t raw_score = output->data.int8[0];
    float confidence = ((float)raw_score + 128.0) / 255.0 * 100.0;

	// DEBUGGING AI suy luận
	Serial.printf("[OUTPUT] Total time: %ld ms | Trust Value: %.1f%% ", duration, confidence);
    Serial.print("[");
    int barWidth = confidence / 5;
    for (int i = 0; i < 20; i++) {
        if (i < barWidth) Serial.print("#");
        else Serial.print(" ");
    }
    Serial.print("] ");

    // 5. NẾU AI PHÁT HIỆN MẶT (>75%), TẠO ẢNH JPEG 600x600 CẮT NÉT ĐỂ UPLOAD
    if (confidence > 75.0) {
        // Vừa dồn dữ liệu hình vuông 600x600 vừa ĐẢO KÊNH MÀU R <-> B bằng tay
        for (int cy = 0; cy < crop_size; cy++) {
            int src_row_start = ((offset_y + cy) * src_w + offset_x) * 3;
            int dst_row_start = (cy * crop_size) * 3;

            for (int cx = 0; cx < crop_size; cx++) {
                int s_idx = src_row_start + cx * 3;
                int d_idx = dst_row_start + cx * 3;

                uint8_t r = rgb_buffer[s_idx + 0];
                uint8_t g = rgb_buffer[s_idx + 1];
                uint8_t b = rgb_buffer[s_idx + 2];

                // Tráo kênh màu Red và Blue để sửa lỗi lệch màu
                rgb_buffer[d_idx + 0] = b;
                rgb_buffer[d_idx + 1] = g;
                rgb_buffer[d_idx + 2] = r;
            }
        }

        // Nén mảng RGB 600x600 ngay tại đầu rgb_buffer
        bool success = fmt2jpg(rgb_buffer, crop_size * crop_size * 3, crop_size, crop_size, PIXFORMAT_RGB888, 85, cropped_jpg_out, cropped_jpg_len);
        
        if (!success || *cropped_jpg_out == NULL) {
            Serial.println("\n[ERROR] fmt2jpg Failed to compress image!");
        }
    }

    free(rgb_buffer); // Dọn dẹp RAM gốc
    return confidence;
}

// ================= MAIN RUN FUNCTION =================
void setup() {
	Serial.begin(115200);
	SerialESP.begin(115200, SERIAL_8N1, RX_ESP_PIN, TX_ESP_PIN);  // Mở cổng phụ nói chuyện với ESP32

	camera_config_t config;
	config.ledc_channel = LEDC_CHANNEL_0;
	config.ledc_timer = LEDC_TIMER_0;
	config.pin_d0 = Y2_GPIO_NUM;
	config.pin_d1 = Y3_GPIO_NUM;
	config.pin_d2 = Y4_GPIO_NUM;
	config.pin_d3 = Y5_GPIO_NUM;
	config.pin_d4 = Y6_GPIO_NUM;
	config.pin_d5 = Y7_GPIO_NUM;
	config.pin_d6 = Y8_GPIO_NUM;
	config.pin_d7 = Y9_GPIO_NUM;
	config.pin_xclk = XCLK_GPIO_NUM;
	config.pin_pclk = PCLK_GPIO_NUM;
	config.pin_vsync = VSYNC_GPIO_NUM;
	config.pin_href = HREF_GPIO_NUM;
	config.pin_sscb_sda = SIOD_GPIO_NUM;
	config.pin_sscb_scl = SIOC_GPIO_NUM;
	config.pin_pwdn = PWDN_GPIO_NUM;
	config.pin_reset = RESET_GPIO_NUM;
	config.xclk_freq_hz = 20000000;
	config.pixel_format = PIXFORMAT_JPEG;

	config.frame_size = FRAMESIZE_SVGA;
	config.jpeg_quality = 10;
	config.fb_count = 1;

	if (esp_camera_init(&config) != ESP_OK) {
		Serial.println("[ERROR] Fail to initilize Camera!");
		return;
	}

	WiFi.disconnect(true);
	delay(100);
	WiFi.mode(WIFI_STA);
	WiFi.begin(ssid, password);

	Serial.print("Attempt to connect WiFi...");
	int attempts = 0;
	while (WiFi.status() != WL_CONNECTED && attempts < 20) {
		delay(500);
		Serial.print(".");
		attempts++;
	}

	if (WiFi.status() != WL_CONNECTED) {
		Serial.println("\n[ERROR] Fail to connect to Wifi, Reconnecting....");
		ESP.restart();
	}
	Serial.println("\n[DEBUG] WiFi Connected!");

	// Set up Mô hình AI ở đây
	Model_Setup();
	Serial.println("[DEBUG] AI Model is fully initilized on ESP32-CAM!");
}

void loop() {
    // Đọc toàn bộ tin nhắn tồn đọng trong bộ đệm Serial
    while (SerialESP.available()) {
        String msg = SerialESP.readStringUntil('\n');
        msg.trim();
        if (msg.startsWith("DOOR:")) {
            int commaIdx = msg.indexOf(',');
            if (commaIdx != -1) {
                String doorStr = msg.substring(5, commaIdx);
                String pendStr = msg.substring(commaIdx + 6);
                isDoorOpen = (doorStr == "1");
                isPending = (pendStr == "1");
            }
        }
    }
    

    // 2. LẤY KHUNG HÌNH GỐC TỪ CAMERA (Ví dụ SVGA 800x600)
    camera_fb_t* fb = esp_camera_fb_get();
    if (!fb) {
        Serial.println("[ERROR] Fail to capture image!\n");
        return;
    } 

    // 3. CHỈ QUÉT AI KHI CỬA KHÉP VÀ KHÔNG PENDING
    if (!isDoorOpen && !isPending) {
        if (millis() - lastScanTime >= scanInterval) {
            lastScanTime = millis();

            // Khai báo con trỏ nhận ảnh JPEG hình vuông sau khi cắt
            uint8_t* cropped_jpg = NULL;
            size_t cropped_len = 0;

            // Gọi hàm vừa nhận diện AI vừa cắt ảnh 600x600
            float confidence = Run_Model_And_Crop(fb, &cropped_jpg, &cropped_len);

            if (confidence > 75.0 && cropped_jpg != NULL) {
                Serial.println("\n[DEBUG] Face Detected - Uploading Cropped High-Res Image...");

                // GỬI ẢNH ĐÃ CẮT (JPEG 600x600) LÊN IMGBB
                ImgBBData imgData = uploadToImgBB(cropped_jpg, cropped_len);
                
                if (imgData.url != "") {
                    Serial.println("      => Link ImgBB: " + imgData.url);	
                    Serial.println("      => Delete URL: " + imgData.delete_url);
                    Serial.println("      => Timestamp: "  + imgData.timestamp);
                    
                    // Gửi thông tin về Firebase
                    updateNewRequest(imgData);
                }

                //Giải phóng bộ nhớ ảnh cắt để không bị tràn PSRAM
                free(cropped_jpg);

                // Tạm hoãn 15 giây để tránh gửi trùng lặp liên tục khi mặt vẫn đứng trước camera
                scanInterval = 30000;
            } else {
                Serial.println("\n[DEBUG] No Face in Image");
                scanInterval = 0;
            }
        }
    } else {
        Serial.println("\n[DEBUG] Door is Opening or Request is Pendind");
        Serial.print("[DEBUG] Is Door Opening   : ");
        Serial.println(isDoorOpen ? "true" : "false");
        Serial.print("[DEBUG] Is Request Pending: ");
        Serial.println(isPending  ? "true" : "false");
    }

    // 4. XẢ KHUNG HÌNH CAMERA GỐC RA NGAY LẬP TỨC
	Serial.println("\n");
    esp_camera_fb_return(fb);
}