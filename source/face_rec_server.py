import time
import sys
from datetime import datetime
from collections import deque
from firebase_admin import db

from firebase_manager import (
    init_firebase, get_new_requests, delete_processed_request, update_ai_status,
    add_history_log, load_registered_db, check_door_alert, clear_door_alert, is_mock
)
from telegram_bot import send_telegram_alert
from face_engine import fetch_image_from_url, get_face_embedding, find_best_match, warmup_ai_model

MAX_LOGS = 20                           # Lưu tối đa 20 dòng log gần nhất
log_queue = deque(maxlen=MAX_LOGS)      # Queue lưu log dạng FIFO
start_time = time.time()                # 

def add_log(message):
    """Thêm log vào queue và in ra terminal dạng text cơ bản"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    log_line = f"[{timestamp}] {message}"
    log_queue.append(log_line)
    print(log_line)  

def sync_to_firebase(uptime_str):
    """Đẩy toàn bộ Log, Uptime và Timestamp lên Firebase để Streamlit UI đọc"""
    if not is_mock("mock_database"):
        try:
            db.reference('server_status/info').set({
                "uptime": uptime_str,
                "last_update": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "logs": list(log_queue)  # Đẩy danh sách log lên web
            })
        except Exception as e:
            print(f"Lỗi đồng bộ Firebase: {e}")

def get_refresh_rate():
    """Đọc cấu hình tốc độ quét từ Firebase"""
    if not is_mock("mock_database"):
        try:
            rate = db.reference('server_status/refresh_rate').get()
            return float(rate) if rate else 3.0
        except Exception:
            pass
    return 3.0

def process_ai_recognition(registered_db):
    """Xử lý nhận diện khuôn mặt (logic giữ nguyên)"""
    try:
        new_requests = get_new_requests()
    except Exception as e:
        add_log(f"⚠️ Lỗi kết nối Database: {e}")
        return

    if check_door_alert():
        add_log("🚨 CẢNH BÁO: Cửa mở quá 3 phút!")
        try:
            send_telegram_alert("🚨 CẢNH BÁO AN NINH!\n⚠️ Cửa phòng đã mở liên tục quá 3 phút!")
        except Exception:
            pass
        clear_door_alert()

    if isinstance(new_requests, dict) and new_requests:
        for req_id, req_data in new_requests.items():
            if isinstance(req_data, dict) and req_data.get("status") == "pending":
                img_url = req_data.get("image_url")
                del_url = req_data.get("delete_img_url", "")
                req_time = req_data.get("timestamp", int(time.time()))
                time_str = datetime.fromtimestamp(req_time).strftime("%Y-%m-%d %H:%M:%S")

                if img_url:
                    add_log(f"📸 Quét Request ID: {req_id}")
                    update_ai_status("pending") 
                    
                    opencv_img, fetch_err = fetch_image_from_url(img_url)

                    if opencv_img is not None:
                        has_samples = any(udata.get("samples") for udata in registered_db.values() if isinstance(udata, dict)) if isinstance(registered_db, dict) else False
                        log_id = f"log_{req_time}"

                        if not has_samples:
                            update_ai_status("unknown")
                            add_log("❌ CSDL trống! Từ chối mở cửa.")
                            add_history_log(log_id, {
                                "timestamp": time_str, "person_name": "Người lạ", 
                                "action": "Từ chối mở cửa (CSDL rỗng)", "image_url": img_url, "delete_img_url": del_url
                            })
                            delete_processed_request(req_id)
                        else:
                            add_log("🧠 Bắt đầu trích xuất đặc trưng...")
                            embedding, bbox, err = get_face_embedding(opencv_img)
                            
                            if not err and embedding is not None:
                                best_name, min_dist, similarity, _ = find_best_match(embedding, registered_db)
                                if "Người lạ" not in best_name:
                                    update_ai_status("known") 
                                    add_log(f"✅ MỞ CỬA: {best_name} ({similarity:.1f}%)")
                                    add_history_log(log_id, {
                                        "timestamp": time_str, "person_name": best_name, 
                                        "action": f"Mở cửa ({similarity:.1f}%)", "image_url": img_url, "delete_img_url": del_url
                                    })
                                else:
                                    update_ai_status("unknown")
                                    add_log(f"🚨 Người lạ! Từ chối mở cửa.")
                                    add_history_log(log_id, {
                                        "timestamp": time_str, "person_name": "Người lạ", 
                                        "action": "Từ chối mở cửa", "image_url": img_url, "delete_img_url": del_url
                                    })
                                delete_processed_request(req_id)
                            else:
                                add_log("⚠️ Ảnh lỗi hoặc không rõ mặt.")
                                delete_processed_request(req_id)
                                
                    time.sleep(1)
                    update_ai_status("idle")
                    add_log("💤 Đang chờ dữ liệu mới...")

def main():
    print("\n" + "="*50)
    print("🚀 AI SERVER ĐANG CHẠY - NHẤN CTRL+C ĐỂ TẮT")
    print("="*50 + "\n")
    
    init_firebase()
    add_log("📡 Đã kết nối Firebase.")
    warmup_ai_model()
    add_log("🤖 AI Model khởi động xong. Sẵn sàng!")
    
    # Set default refresh rate = 3.0 nếu chưa có
    if not is_mock("mock_database") and db.reference('server_status/refresh_rate').get() is None:
        db.reference('server_status/refresh_rate').set(3.0)

    last_db_check = 0
    registered_db = {}

    while True:
        try:
            if time.time() - last_db_check > 15 or not registered_db:
                registered_db, _, _ = load_registered_db()
                last_db_check = time.time()

            current_rate = get_refresh_rate()
            process_ai_recognition(registered_db)
            
            # Tính Uptime
            uptime_seconds = int(time.time() - start_time)
            hours, remainder = divmod(uptime_seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            uptime_str = f"{hours:02d}h {minutes:02d}m {seconds:02d}s"

            # Đẩy mọi thứ lên Firebase để UI vẽ ra
            sync_to_firebase(uptime_str)
            
            time.sleep(current_rate)

        except KeyboardInterrupt:
            sync_to_firebase("00h 00m 00s")
            print("\n\n🛑 Đã ngắt Server thành công!")
            break
        except Exception as e:
            add_log(f"💥 Lỗi: {e}")
            time.sleep(2)

if __name__ == "__main__":
    main()