# import firebase_admin
# from firebase_admin import credentials, db
# import streamlit as st

# @st.cache_resource
# def init_firebase():
#     """Khởi tạo Firebase an toàn. Trả về (Trạng thái, Lời nhắn)"""
#     try:
#         # Nếu chưa có app nào được khởi tạo
#         if not firebase_admin._apps:
#             # Kiểm tra xem có cấu hình trong secrets chưa
#             if "firebase" not in st.secrets:
#                 return False, "Chưa tìm thấy cấu hình [firebase] trong secrets.toml"
                
#             cred_dict = dict(st.secrets["firebase"])
#             db_url = cred_dict.pop("database_url", None)
            
#             if not db_url:
#                 return False, "Thiếu database_url trong cấu hình."
                
#             # Xử lý an toàn chuỗi private_key
#             if "\\n" in cred_dict["private_key"]:
#                 cred_dict["private_key"] = cred_dict["private_key"].replace("\\n", "\n")
                
#             cred = credentials.Certificate(cred_dict)
#             firebase_admin.initialize_app(cred, {'databaseURL': db_url})
            
#         return True, "✅ Kết nối Firebase thành công!"
#     except Exception as e:
#         return False, f"❌ Lỗi khởi tạo Firebase: {str(e)}"

# def get_new_requests():
#     try:
#         return db.reference('new_request').get()
#     except Exception as e:
#         st.toast(f"Lỗi đọc yêu cầu: {e}")
#         return None

# def get_history_logs():
#     try:
#         return db.reference('history_log').get()
#     except Exception as e:
#         st.toast(f"Lỗi đọc lịch sử: {e}")
#         return None

# def update_request_status(req_id, status):
#     db.reference('new_request').child(req_id).update({'status': status})

# def add_history_log(log_data):
#     db.reference('history_log').push(log_data)

# def get_registered_faces():
#     """Lấy danh sách vector đặc trưng từ Firebase (Load 1 lần mỗi chu kỳ kiểm tra)"""
#     return db.reference('registered').get()

# def register_new_face(name, embedding):
#     """Lưu vector khuôn mặt lên Firebase"""
#     db.reference('registered').push({
#         'name': name,
#         'embedding': embedding
#     })


import streamlit as st
import time

# CHẾ ĐỘ GIẢ LẬP (MOCK MODE)
# Không cần import firebase_admin hay credentials

@st.cache_resource
def init_firebase():
    """Giả lập khởi tạo Firebase an toàn. Trả về (Trạng thái, Lời nhắn)"""
    return True, "⚠️ Đang chạy ở chế độ MÔ PHỎNG (Mock Mode) - Không cần Key Firebase!"

def get_new_requests():
    """
    Giả lập lấy yêu cầu mở cửa. 
    Trả về None để tab 1 (Engine) ở trạng thái chờ, không bị văng lỗi tải ảnh.
    """
    return None

def get_history_logs():
    """
    Bơm dữ liệu giả để Tab 2 (Dashboard) có bảng thống kê hiển thị ngay lập tức.
    """
    return {
        "mock_log_001": {
            "timestamp": "2026-07-16 08:30:00",
            "image_url": "./source/Face_History/cat.png",
            "person_name": "Tiến Lưu (Gay)",
            "action": "Mở cửa thành công",
            "bbox": {"x": 50, "y": 50, "w": 100, "h": 100}
        },
        "mock_log_002": {
            "timestamp": "2026-07-16 09:15:22",
            "image_url": "./source/Face_History/Imposter.png",
            "person_name": "Người lạ",
            "action": "Từ chối mở cửa",
            "bbox": {"x": 60, "y": 40, "w": 90, "h": 110}
        }
    }

def update_request_status(req_id, status):
    """Giả lập cập nhật trạng thái (Bỏ qua vì không có Database thật)"""
    pass

def add_history_log(log_data):
    """Giả lập thêm lịch sử (Bỏ qua vì không có Database thật)"""
    pass

def get_registered_faces():
    """
    Lấy danh sách vector đặc trưng. 
    Trả về dictionary rỗng để hàm AI không bị lỗi khi so sánh.
    """
    return {}

def register_new_face(name, embedding):
    """
    Giả lập lưu vector khuôn mặt lên Firebase.
    Sử dụng time.sleep để tạo cảm giác "đang tải lên mạng" giống thật.
    """
    time.sleep(1.5)
    pass