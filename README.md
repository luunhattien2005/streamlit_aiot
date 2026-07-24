# streamlit_aiot

Built for web dashboards and lightweight face recognition hosting using Streamlit.

To run streamlit local, install `streamlit and all req libs`, then run `streamlit run <file python>`

```Markdown
streamlit run .\source\streamlit_app.py
```

Global hosting at: [esp32cam.streamlit.app](https://esp32cam.streamlit.app/)

Notes:

* Python: `3.13`.
* Main file path on deploy: `source/streamlit_app.py`.
* When deployed, main file path can not be changed (deploy a new one instead if needed).

## 📖 Hướng Dẫn Sử Dụng

Giao diện ứng dụng được chia thành 3 Tabs:

* **Tab 1 - ⚙️ Lắng Nghe Mở Cửa** : Đây là engine chạy ngầm, auto-refresh mỗi 2 giây để quét các yêu cầu mở cửa mới từ Firebase. Khi phát hiện có người, hệ thống tải ảnh, trích xuất vector khuôn mặt và so sánh với dữ liệu người nhà.
* **Tab 2 - 📊 Lịch Sử Ra Vào** : Bảng Dashboard thống kê toàn bộ lịch sử ra vào (thời gian, tên người, hành động mở/từ chối).
* **Tab 3 - 👤 Đăng ký Khuôn Mặt** : Giao diện thêm người dùng mới vào hệ thống. Bạn nhập tên, tải ảnh lên, AI sẽ trích xuất vector Embedding và lưu thẳng lên Firebase. Khuyến khích đăng ký nhiều góc mặt cho cùng một người để tăng độ chính xác.

## 🗄️ Database Schema (Firebase)

Hệ thống lưu trữ trên Firebase Realtime Database với 3 nhánh chính:

**1. `new_request`** (Nhánh chờ xử lý mở cửa)
Lưu các tín hiệu yêu cầu mở cửa gửi lên từ ESP32-CAM.

* `req_<timestamp>`: String.
  * `status`: "pending".
  * `image_url`: String (Link ảnh tải về từ ImgBB).
  * `delete_img_url`: String (Link dùng để xóa ảnh trên ImgBB).
  * `timestamp`: Int.

**2. `history_log`** (Nhánh lịch sử)
Lưu lại toàn bộ kết quả sau khi AI xử lý xong.

* `log_<timestamp>`: String
  * `timestamp`: String (YYYY-MM-DD HH:MM:SS).
  * `image_url`: String (Link ảnh).
  * `person_name`: String (Tên người được nhận diện hoặc "Người lạ").
  * `action`: String ("Mở cửa thành công (XX.X%)" | "Từ chối mở cửa").
  * `delete_img_url`: String (Link dùng để xóa ảnh trên ImgBB).


**3. `registered`** (Nhánh dữ liệu người dùng)
Lưu trữ thông tin nhận diện khuôn mặt.

* `user_<timestamp>`: String
  * `name`: String (Tên người dùng).
  * `samples`:
    * `sample_<timestamp>`:
      * `delete_img_url`: String (Link dùng để xóa ảnh trên ImgBB).
      * `embedding`: String (encode Base64 từ vector đặc trưng ảnh).
      * `image_url`: String (Link ảnh).
  * `updated_at`: String (YYYY-MM-DD HH:MM:SS).      

## 🔄 Luồng Hoạt Động (System Flow)

1. Khách đến nhấn chuông/quét mặt -> ESP32-CAM chụp ảnh và gửi lên ImgBB, sau đó đẩy link ảnh kèm trạng thái `pending` vào nhánh `new_request` trên Firebase.
2. Tab Engine (`streamlit_app.py`) phát hiện `pending` -> Tải ảnh về -> Gọi DeepFace trích xuất vector đặc trưng bằng model `VGG-Face`.
3. Hệ thống quét toàn bộ nhánh `registered` để tính toán khoảng cách Cosine Distance (Ngưỡng/Threshold chuẩn = 0.68). <- Sẽ tham khảo update cách khác brute force khi có thời gian
4. Trả kết quả: Ra lệnh mở cửa (nếu < 0.68) hoặc từ chối (nếu >= 0.68).
5. Cập nhật nhánh `new_request` thành `completed` và ghi dữ liệu vào `history_log`.

## ⚠️ Cảnh báo Thiết Lập (Secrets & Database)

Dự án này sử dụng cơ chế bảo mật của Streamlit thông qua file `.streamlit/secrets.toml` để kết nối Firebase.

* **Vui lòng liên hệ trực tiếp chủ dự án** để nhận nội dung file secret này.

