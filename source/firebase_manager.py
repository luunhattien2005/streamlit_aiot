import firebase_admin
from firebase_admin import credentials, db
import streamlit as st
import time
import os
import json
import base64
import numpy as np
import cv2
import requests

def is_mock(flag_name):
    """Hàm kiểm tra flag trong secrets.toml"""
    return "dev" in st.secrets and st.secrets["dev"].get(flag_name, False)

@st.cache_resource
def init_firebase():
    """Khởi tạo kết nối tới Firebase Realtime Database"""
    if not firebase_admin._apps:
        try:
            fb_config = dict(st.secrets["firebase"])
            db_url = fb_config.get("database_url") or fb_config.get("databaseURL")
            if not db_url or "your-database-name" in db_url:
                st.error("❌ Cảnh báo: Chưa cấu hình đúng `database_url` trong file .streamlit/secrets.toml!")
                return
            cred = credentials.Certificate(fb_config)
            firebase_admin.initialize_app(cred, {'databaseURL': db_url})
        except Exception as e:
            st.error(f"Lỗi khi khởi tạo Firebase: {e}")

# ==========================================
# CÁC HÀM QUẢN LÝ TÀI KHOẢN ADMIN
# ==========================================
def get_admin_credentials_from_db():
    """Lấy cả Username và Password Admin từ Firebase"""
    if not is_mock("mock_database"):
        try:
            data = db.reference('admin_settings').get()
            if isinstance(data, dict):
                return data.get("web_username"), data.get("web_password")
        except Exception as e:
            st.error(f"Lỗi khi đọc thông tin Admin từ Firebase: {e}")
    return None, None

def update_admin_credentials_in_db(new_username, new_password):
    """Cập nhật cả Username và Password Admin mới lên Firebase"""
    if not is_mock("mock_database"):
        try:
            db.reference('admin_settings').update({
                'web_username': new_username,
                'web_password': new_password
            })
            return True
        except Exception as e:
            st.error(f"Lỗi khi lưu thông tin Admin mới lên Firebase: {e}")
            return False
    return False

# ==========================================
# CÁC HÀM XỬ LÝ NEW REQUEST & HISTORY LOG
# ==========================================
def get_new_requests():
    return db.reference('new_request').get()

def get_history_logs():
    if is_mock("mock_history"):
        return {
            "mock_log_001": {
                "timestamp": "2026-07-16 08:30:00",
                "image_url": "https://i.ibb.co/sdXDdqBt/capture.jpg",
                "person_name": "Tiến Lưu (Mock)",
                "action": "Mở cửa thành công",
            }
        }
    return db.reference('history_log').get()

def delete_processed_request(req_id):
    """Xóa request khỏi nhánh chờ sau khi đã xử lý và lưu vào lịch sử"""
    if not is_mock("mock_database"):
        db.reference('new_request').child(req_id).delete()

def add_history_log(log_id, log_data):
    """Lưu lịch sử với một ID tùy chọn"""
    if not is_mock("mock_database"):
        db.reference('history_log').child(log_id).set(log_data)

def push_esp32_mock_request(image_url, delete_url, img_time):
    """Giả lập ESP32 đẩy link ảnh lên Firebase nhánh chờ duyệt"""
    if not is_mock("mock_database"):
        req_id = f"req_{img_time}" 
        db.reference('new_request').child(req_id).set({
            'image_url': image_url,
            'delete_img_url': delete_url,
            'timestamp': img_time,
            'status': 'pending'
        })
        return req_id
    return None

def delete_history_log(log_id):
    if not is_mock("mock_database"):
        try: db.reference('history_log').child(log_id).delete()
        except Exception as e: st.error(f"Lỗi khi xóa log Firebase: {e}")

def get_device_status():
    """
    Đọc trạng thái THẬT do chính ESP32 báo cáo (nhánh device_status, một chiều
    thiết bị -> web). Web PHẢI đọc nhánh này để hiển thị đúng khi trạng thái
    thay đổi do chính thiết bị gây ra (bấm mật khẩu bàn phím, cảm biến MC-38
    tự khóa lại...), chứ không chỉ dựa vào lệnh web vừa gửi đi (device_control).
    """
    if not is_mock("mock_database"):
        try:
            return db.reference('device_status').get() or {}
        except Exception as e:
            st.error(f"Lỗi khi đọc trạng thái thiết bị: {e}")
            return {}
    return {}

def check_door_alert():
    """Kiểm tra cảnh báo cửa mở quá lâu từ ESP32"""
    if not is_mock("mock_database"):
        return db.reference('device_control/door_alert').get()
    return None

def clear_door_alert():
    """Xóa trạng thái cảnh báo sau khi đã gửi Telegram"""
    if not is_mock("mock_database"):
        db.reference('device_control/door_alert').delete()

# ==========================================
# CÁC HÀM QUẢN LÝ KHO DỮ LIỆU & VECTOR
# ==========================================
def encode_vector(emb_list):
    """Nén mảng float thành chuỗi Base64"""
    return base64.b64encode(np.array(emb_list, dtype=np.float32).tobytes()).decode('utf-8')

def decode_vector(b64_str):
    """Giải mã chuỗi Base64 về lại mảng float"""
    if isinstance(b64_str, list): return b64_str 
    return np.frombuffer(base64.b64decode(b64_str), dtype=np.float32).tolist()

def upload_to_imgbb(opencv_rgb_img):
    """Upload ảnh trực tiếp lên ImgBB"""
    _, buffer = cv2.imencode('.jpg', cv2.cvtColor(opencv_rgb_img, cv2.COLOR_RGB2BGR))
    encoded_img = base64.b64encode(buffer).decode('utf-8')
    api_key = st.secrets["imgbb"]["api_key"]
    res = requests.post("https://api.imgbb.com/1/upload", data={"key": api_key, "image": encoded_img})
    if res.status_code == 200:
        data = res.json()["data"]
        return data["url"], data["delete_url"]
    return None, None

def save_registered_db(reg_db, is_mock_db, json_path):
    """Đồng bộ dữ liệu xuống Local JSON hoặc Firebase"""
    db_to_save = {}
    for uid, user_data in reg_db.items():
        if not isinstance(user_data, dict): continue
        db_to_save[uid] = {
            "name": user_data.get("name", ""),
            "updated_at": user_data.get("updated_at", ""),
            "samples": {}
        }
        for sid, sdata in user_data.get("samples", {}).items():
            if not isinstance(sdata, dict): continue
            emb = sdata.get("embedding")
            encoded_emb = encode_vector(emb) if isinstance(emb, (list, np.ndarray)) else emb
            
            sample_dict = {"embedding": encoded_emb}
            if "image_path" in sdata: sample_dict["image_path"] = sdata["image_path"]
            if "image_url" in sdata: sample_dict["image_url"] = sdata["image_url"]
            if "delete_img_url" in sdata: sample_dict["delete_img_url"] = sdata["delete_img_url"]
            db_to_save[uid]["samples"][sid] = sample_dict

    if is_mock_db:
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(db_to_save, f, ensure_ascii=False, indent=4)
    else:
        ref = db.reference("registered")
        if db_to_save: ref.set(db_to_save)
        else: ref.delete() 

def load_registered_db():
    """Tải và giải mã Base64 vector từ Local JSON hoặc Firebase"""
    is_mock_db = is_mock("mock_database")
    DB_DIR = "./source/Face_Database"
    JSON_PATH = os.path.join(DB_DIR, "registered_db.json")
    os.makedirs(DB_DIR, exist_ok=True)
    
    if is_mock_db:
        if os.path.exists(JSON_PATH):
            try:
                with open(JSON_PATH, "r", encoding="utf-8") as f: db_data = json.load(f)
            except Exception: db_data = {}
        else: db_data = {}
    else:
        try: db_data = db.reference("registered").get() or {}
        except Exception: db_data = {}

    if not isinstance(db_data, dict): db_data = {}

    for uid, user_data in db_data.items():
        if isinstance(user_data, dict) and "samples" in user_data:
            for sid, sample_data in user_data["samples"].items():
                if isinstance(sample_data, dict) and "embedding" in sample_data:
                    sample_data["embedding"] = decode_vector(sample_data["embedding"])
                    
    return db_data, is_mock_db, JSON_PATH