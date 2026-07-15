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

* `req_id`: String.
  * `status`: "pending" | "completed".
  * `image_url`: String (Link ảnh tải về từ ImgBB).

**2. `history_log`** (Nhánh lịch sử)
Lưu lại toàn bộ kết quả sau khi AI xử lý xong.

* `log_id`: String
  * `timestamp`: String (YYYY-MM-DD HH:MM:SS).
  * `image_url`: String (Link ảnh).
  * `person_name`: String (Tên người được nhận diện hoặc "Người lạ").
  * `action`: String ("Mở cửa thành công" | "Từ chối mở cửa").
  * `bbox`: Object `{x, y, w, h}` (Tọa độ khuôn mặt).

**3. `registered`** (Nhánh dữ liệu người dùng)
Lưu trữ thông tin nhận diện khuôn mặt.

* `user_id`: String
  * `name`: String (Tên người dùng).
  * `embedding`: Array (Mảng vector đặc trưng trích xuất từ ảnh).

## 🔄 Luồng Hoạt Động (System Flow)

1. Khách đến nhấn chuông/quét mặt -> ESP32-CAM chụp ảnh và gửi lên ImgBB, sau đó đẩy link ảnh kèm trạng thái `pending` vào nhánh `new_request` trên Firebase.
2. Tab Engine (`streamlit_app.py`) phát hiện `pending` -> Tải ảnh về -> Gọi DeepFace trích xuất vector đặc trưng bằng model `VGG-Face`.
3. Hệ thống quét toàn bộ nhánh `registered` để tính toán khoảng cách Cosine Distance (Ngưỡng/Threshold chuẩn = 0.68). <- Sẽ tham khảo update cách khác brute force khi có thời gian
4. Trả kết quả: Ra lệnh mở cửa (nếu < 0.68) hoặc từ chối (nếu >= 0.68).
5. Cập nhật nhánh `new_request` thành `completed` và ghi dữ liệu vào `history_log`^^.

## ⚠️ Cảnh báo Thiết Lập (Secrets & Database)

Dự án này sử dụng cơ chế bảo mật của Streamlit thông qua file `.streamlit/secrets.toml` để kết nối Firebase.

* **Vui lòng liên hệ trực tiếp chủ dự án** để nhận nội dung file secret này.
* Cần phối hợp với người thiết kế database để đảm bảo cấu trúc `private_key` (chuỗi PEM) và các field khác được truyền vào đúng định dạng, tránh lỗi `InvalidByte` khi giải mã chứng chỉ.

## 🧪 Chế Độ Giả Lập (Mock Mode) & Tình Trạng Dự Án

Hiện tại, dự án vẫn đang trong giai đoạn  **Framework cần hoàn thiện và kết nối** .

Để thuận tiện cho việc phát triển giao diện (UI/UX) mà không bị phụ thuộc hoặc gây lỗi do thiếu Key Firebase, hệ thống đã làm tạm **Mock Mode (Chế độ giả lập)** trong file `firebase_manager.py`.

* Khi Mock Mode được sử dụng, ứng dụng sẽ bypass hoàn toàn Firebase.
* Các nhánh dữ liệu sẽ tạo sẵn dummy data để giao diện ở các Tab hoạt động, hiển thị bảng biểu bình thường.
* Việc phân tích AI vẫn hoạt động nhưng kết quả sẽ không được lưu lên cloud.

## 💡 Ghi chú Nhận Diện Khác Thiết Bị (Cross-Device Recognition)

Ảnh dùng để đăng ký khuôn mặt có thể được chụp bằng **điện thoại di động** rồi tải lên thông qua UI. Dữ liệu vector này **hoàn toàn có thể** dùng để đối chiếu với ảnh quét mặt ngoài cửa chụp bằng  **ESP32-CAM** .
Bởi vì bản chất thuật toán Deep Learning trích xuất cấu trúc đặc trưng sinh trắc học của khuôn mặt (khoảng cách hốc mắt, xương hàm...) thay vì dựa vào độ sắc nét phần cứng của camera. (Ghi chú: Cần thử nghiệm thực tế thêm để tìm ra góc sáng và độ nhiễu tối ưu nhất cho ESP32-CAM)
