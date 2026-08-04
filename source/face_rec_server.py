import time
from datetime import datetime
from collections import deque
from firebase_admin import db

from firebase_manager import (
    init_firebase, get_new_requests, delete_processed_request, update_ai_status,
    add_history_log, load_registered_db, check_door_alert, clear_door_alert, is_mock
)
from telegram_bot import send_telegram_alert
from face_engine import fetch_image_from_url, get_face_embedding, find_best_match, warmup_ai_model, FACENET_THRESHOLD, VGG_FACE_THRESHOLD

MAX_LOGS = 15                           # Lưu tối đa 15 dòng log gần nhất
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
            send_telegram_alert("🚨 CẢNH BÁO!\n⚠️ Cửa phòng đã mở liên tục quá 3 phút!")
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
                                "action": "Từ chối (CSDL rỗng)", "image_url": img_url, "delete_img_url": del_url
                            })

                            try:
                                msg = f"⚠️ *THÔNG BÁO* ⚠️\nCó người cố gắng quét mặt lúc {time_str}, nhưng CSDL hiện đang trống!"
                                send_telegram_alert(msg, image_url=img_url)
                            except Exception:
                                pass

                            delete_processed_request(req_id)
                        else:
                            add_log("🧠 Bắt đầu trích xuất đặc trưng...")
                            embedding, bbox, err = get_face_embedding(opencv_img)
                            
                            if not err and embedding is not None:

                                best_name, min_dist, similarity, _ = find_best_match(embedding, registered_db)
                                threshold_percent = (1.0 - FACENET_THRESHOLD) * 100

                                if "Người lạ" not in best_name:
                                    update_ai_status("known") 
                                    add_log(f"✅ MỞ CỬA: {best_name} ({similarity:.1f}% / {threshold_percent:.1f}%).")
                                    add_history_log(log_id, {
                                        "timestamp": time_str, 
                                        "person_name": best_name, 
                                        "action": f"Mở cửa ({similarity:.1f}%/{threshold_percent:.1f}%)", 
                                        "image_url": img_url, 
                                        "delete_img_url": del_url
                                    })

                                else:
                                    update_ai_status("unknown")
                                    add_log(f"🚨 Người lạ! Từ chối mở cửa ({similarity:.1f}% / {threshold_percent:.1f}%).")
                                    add_history_log(log_id, {
                                        "timestamp": time_str, 
                                        "person_name": "Người lạ", 
                                        "action": f"Từ chối ({similarity:.1f}%/{threshold_percent:.1f}%)", 
                                        "image_url": img_url, 
                                        "delete_img_url": del_url
                                    })

                                    # Gửi Telegram
                                    try:
                                        msg = f"🚨 *CẢNH BÁO* 🚨\nPhát hiện người lạ lúc {time_str}!\nĐộ nhận diện: {similarity:.1f}% (Ngưỡng yêu cầu: {threshold_percent:.1f}%)"
                                        send_telegram_alert(msg, image_url=img_url)
                                    except Exception:
                                        pass

                                delete_processed_request(req_id)
                            else:
                                add_log("⚠️ Ảnh lỗi hoặc không rõ mặt.")
                                delete_processed_request(req_id)
                                
                    time.sleep(1)
                    update_ai_status("idle")
                    add_log("💤 Đang chờ dữ liệu mới...")

def main():
    print("\n" + "="*50)
    print("🚀 FACE RECOGNITION SERVER ĐANG CHẠY - NHẤN CTRL+C ĐỂ TẮT")
    print("="*50 + "\n")
    
    init_firebase()
    add_log("📡 Đã kết nối Firebase.")
    warmup_ai_model()
    add_log("🤖 AI Model khởi động xong.")
    
    # Set default refresh rate = 3.0 nếu chưa có
    if not is_mock("mock_database") and db.reference('server_status/refresh_rate').get() is None:
        db.reference('server_status/refresh_rate').set(3.0)

    last_db_check = 0
    registered_db = {}

    last_user_count = -1
    last_sample_count = -1

    while True:
        try:
            # Quét DB mỗi 30 giây hoặc khi DB đang trống
            if time.time() - last_db_check > 30 or not registered_db:
                new_db, _, _ = load_registered_db()
                last_db_check = time.time()
                
                # Đếm tổng số người và tổng số ảnh hiện có
                users_count = len(new_db)
                samples_count = sum(len(u.get("samples", {})) for u in new_db.values() if isinstance(u, dict))
                
                # Chỉ ghi log nếu CSDL có sự thay đổi (thêm/bớt người, thêm/bớt ảnh) hoặc lần đầu khởi chạy
                if users_count != last_user_count or samples_count != last_sample_count:
                    registered_db = new_db
                    add_log(f"🔄 Đã tải CSDL Face: {users_count} người, tổng {samples_count} ảnh.")
                    
                    # Liệt kê chi tiết từng người
                    for uid, udata in registered_db.items():
                        if isinstance(udata, dict):
                            name = udata.get("name", "Unknown")
                            img_count = len(udata.get("samples", {}))
                            add_log(f"   👤 {name}: {img_count} ảnh")
                            
                    # Cập nhật lại mốc so sánh
                    last_user_count = users_count
                    last_sample_count = samples_count

            current_rate = get_refresh_rate()
            process_ai_recognition(registered_db)
            
            # Tính Uptime
            uptime_seconds = int(time.time() - start_time)
            hours, remainder = divmod(uptime_seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            uptime_str = f"{hours:02d}h {minutes:02d}m {seconds:02d}s"

            # Đẩy mọi thứ lên Firebase để UI cập nhật
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