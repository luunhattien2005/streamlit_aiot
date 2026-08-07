# 🚪 streamlit_aiot - Smart Door Access Control & Dashboard

Hệ thống quản lý ra vào thông minh kết hợp AIoT (ESP32-CAM) và AI (Nhận diện khuôn mặt với DeepFace), kết nối Realtime qua Firebase và điều khiển trực quan bằng Streamlit Dashboard.

🌐 **Global Hosting:** [esp32cam.streamlit.app](https://esp32cam.streamlit.app/)

---

## 💻 Hướng Dẫn Cài Đặt & Vận Hành

### Yêu cầu môi trường

* **Python:** `3.13.x`
* **Cấu hình Deploy:** File chạy chính trên cloud là `source/streamlit_app.py`.

### Khởi chạy ứng dụng

* **Chạy Streamlit Dashboard (Web App):**

  ```bash
  streamlit run .\source\streamlit_app.py
  ```
* **Chạy Server Nhận Diện Khuôn Mặt (Local):**

  ```bash
  python .\source\face_rec_server.py
  ```

---

## 📖 Chức Năng Các Tab Chính Trên Dashboard

* **Tab 1 - ⚙️ Lắng Nghe & Điều Khuển:** Engine chạy ngầm tự động quét yêu cầu mở cửa từ ESP32-CAM, đồng thời cho phép điều khiển thủ công thiết bị (đóng/mở cửa, bật/tắt đèn, đổi mật khẩu Keypad, trạng thái AI).
* **Tab 2 - 📊 Lịch Sử Ra Vào:** Dashboard thống kê nhật ký ra vào chi tiết (thời gian, hình ảnh, tên người dùng/người lạ, tỷ lệ nhận diện %, hành động).
* **Tab 3 - 👤 Đăng Ký Khuôn Mặt:** Thêm người dùng mới vào hệ thống. Tải ảnh lên để AI trích xuất vector embedding và lưu thẳng lên Firebase.

---

## 🗄️ Cấu Trúc Database (Firebase Realtime Database Schema)

Dữ liệu hệ thống được đồng bộ thời gian thực thông qua 6 nhánh chính:

| Nhánh Node        | Mô Tả                                        | Cấu Trúc Dữ Liệu Chi Tiết                                                                                                                                                                                                                                                                                                                                                                |
| :----------------- | :--------------------------------------------- | :-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `admin_settings` | Cấu hình quản trị & Bot Telegram           | •`telebot_mode`: String (`"Bật"` \| `"Tắt"`)• `web_username`: String (Tên đăng nhập Admin)• `web_password`: String (Mật khẩu Admin)                                                                                                                                                                                                                                      |
| `device_control` | Lệnh điều khiển thiết bị từ xa          | •`ai_status`: `{ timestamp: Int, value: "idle" \| "processing" }`• `door`: `{ timestamp: Int, value: "open" \| "close" }`• `light`: `{ timestamp: Int, value: "on" \| "off" }`• `pass_keypad`: `{ timestamp: Int, value: "123456" }`                                                                                                                                         |
| `device_status`  | Phản hồi trạng thái phần cứng thực tế  | •`light_inside`: String (`"on"` \| `"off"`)• `lock`: String (`"locked"` \| `"unlocked"`)                                                                                                                                                                                                                                                                                        |
| `new_request`    | Tín hiệu chờ xử lý mở cửa từ ESP32-CAM | •`req_<timestamp>`:  - `status`: String (`"pending"` \| `"completed"`)  - `image_url`: String (Link ảnh ImgBB)  - `delete_img_url`: String (Link xóa ảnh ImgBB)  - `timestamp`: Int                                                                                                                                                                                         |
| `history_log`    | Nhật ký lịch sử ra vào                    | •`log_<timestamp>`:  - `person_name`: String (Tên người dùng hoặc `"Người lạ"`)  - `action`: String (Ví dụ: `"Mở cửa (82.8%/67.0%)"`, `"Từ chối (49.7%/67.0%)"`, `"Từ chối mở cửa (CSDL rỗng)"`)  - `image_url`: String (Link ảnh sự kiện)  - `delete_img_url`: String (Link xóa ảnh sự kiện)  - `timestamp`: String (`YYYY-MM-DD HH:MM:SS`) |
| `registered`     | Cơ sở dữ liệu khuôn mặt                  | •`user_<timestamp>`:  - `name`: String (Tên người dùng)  - `updated_at`: String (`YYYY-MM-DD HH:MM:SS`)  - `samples` $\rightarrow$ `sample_<timestamp>`: `{ delete_img_url, embedding, image_url }`                                                                                                                                                                      |

> *Ghi chú:* Nhánh `new_request` sẽ tự động xóa sau khi AI xử lý xong và ghi nhật ký vào `history_log`.

---

## 🔄 Luồng Hoạt Động (System Flow)

1. **Gửi yêu cầu:** Khách nhấn chuông / Quét mặt $\rightarrow$ ESP32-CAM chụp ảnh, upload lên ImgBB và đẩy link kèm trạng thái `pending` vào nhánh `new_request`.
2. **Xử lý AI:** Engine AI trích xuất vector đặc trưng (Embedding) từ ảnh mới và so sánh khoảng cách Cosine Distance với dữ liệu ở nhánh `registered`.
3. **Quyết định:**
   * Tỷ lệ khớp vượt ngưỡng quy định (VD: `> 67.0%`): Cập nhật `device_control/door` thành `"open"`.
   * Tỷ lệ khớp không đạt hoặc CSDL rỗng: Giữ cửa khóa và gán tên `"Người lạ"`.
4. **Phản hồi & Đồng bộ:**
   * Ghi nhận kết quả vào `history_log` kèm tỷ lệ phần trăm nhận diện.
   * Nếu `telebot_mode` đang `"Bật"`, gửi cảnh báo/thông báo kèm hình ảnh qua Telegram.
   * Xóa request trong `new_request`.
5. **Điều khiển mở rộng:** Admin có thể chủ động điều khiển đèn (`light`), đóng/mở cửa (`door`), hoặc đổi mật khẩu bàn phím (`pass_keypad`) trực tiếp từ xa trên Web Dashboard.

---

## ⚠️ Thiết Lập Bảo Mật (Secrets)

Dự án sử dụng cơ chế Streamlit Secrets (`.streamlit/secrets.toml`) để lưu thông tin kết nối Firebase.

Vui lòng tạo file `.streamlit/secrets.toml` theo định dạng mẫu hoặc liên hệ chủ dự án để nhận key:

```toml
[firebase]
type = "service_account"
project_id = "..."
private_key_id = "..."
private_key = "..."
client_email = "..."
client_id = "..."
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "..."
universe_domain = "googleapis.com"
database_url = "..."

[telegram]
bot_token = "..."
chat_id = "..."

[imgbb]
api_key = "..."

[dev]
mock_database = false  
mock_history = false   

[admin] # for mock db
username = "..."
password = "..."
```
