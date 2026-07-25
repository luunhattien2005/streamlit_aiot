import streamlit as st
import time
import pandas as pd
from datetime import datetime
import json
import os
import cv2
import numpy as np
from streamlit_autorefresh import st_autorefresh

from hardware_control import (
    update_ai_status, remote_open_door, remote_lock_door, 
    update_light_mode, change_keypad_password
)

from firebase_manager import (
    init_firebase, get_new_requests, get_history_logs, delete_processed_request, add_history_log,
    load_registered_db, save_registered_db, upload_to_imgbb, check_door_alert, clear_door_alert
)
from telegram_bot import send_telegram_alert
from face_engine import (fetch_image_from_url, get_face_embedding, find_best_match, warmup_ai_model)

init_firebase()   
warmup_ai_model() 

# ========================================================
# HÀM HỖ TRỢ XỬ LÝ POP-UP IMGBB (ROLLBACK COMPONENT V1)
# ========================================================
def open_urls_in_new_tabs(urls):
    """Mở tab mới bằng component.v1 kết hợp thời gian trễ"""
    if isinstance(urls, str): 
        urls = [urls]
        
    js_code = "".join([f"window.open('{u}', '_blank');" for u in urls if u and u.startswith("http")])
    
    if js_code:
        import streamlit.components.v1 as components
        # Gọi Component V1 và ép height=0 để nó tàng hình trên giao diện
        components.html(f"<script>{js_code}</script>", height=0)

st.set_page_config(page_title="Hệ thống Cửa thông minh AIoT", layout="wide")

with open("source/style.css", "r", encoding="utf-8") as f:
    custom_css = f.read()
st.markdown(f"<style>{custom_css}</style>", unsafe_allow_html=True)

# Khởi tạo Session State
if "logged_in" not in st.session_state: st.session_state.logged_in = False
if "show_change_pw" not in st.session_state: st.session_state.show_change_pw = False
if "main_password" not in st.session_state: st.session_state.main_password = "123456"
# ĐỒNG BỘ VỚI DB
if "sync_initial" not in st.session_state:
    # 1. Khởi tạo mặc định dự phòng
    st.session_state.door_locked = True
    st.session_state.light_mode = "Auto"
    st.session_state.light_on = False
    st.session_state.telebot_mode = "Tắt"
    
    # 2. Chủ động móc vào Firebase để lấy trạng thái thật của thiết bị ngay khi tải trang
    from firebase_manager import db, is_mock
    if not is_mock("mock_database"):
        try:
            current_status = db.reference('device_control').get()
            if current_status:
                # Cập nhật trạng thái Cửa
                door_val = current_status.get("door", {}).get("value")
                if door_val == "open": 
                    st.session_state.door_locked = False
                
                # Cập nhật trạng thái Đèn
                light_val = current_status.get("light", {}).get("value")
                mode_map_reverse = {"on": "Bật", "off": "Tắt", "auto": "Auto"}
                if light_val in mode_map_reverse:
                    st.session_state.light_mode = mode_map_reverse[light_val]
                    st.session_state.light_on = (light_val == "on")
        except Exception as e:
            pass
            
    st.session_state.sync_initial = True

# ========================================================
# --- CÁC HOẠT ĐỘNG NGẰM TRONG TRANG WEB ---
# ========================================================
if st.session_state.get("auto_sync", True):
    st_autorefresh(interval=10000, key="auto_check_new_request")

registered_db, is_mock_db, JSON_PATH = load_registered_db()

try: new_requests = get_new_requests()
except Exception: new_requests = {}

# --- LOGIC XỬ LÝ CẢNH BÁO 180S ---
door_alert = check_door_alert()
if door_alert:
    st.toast("🚨 CẢNH BÁO: Cửa mở liên tục quá 3 phút!", icon="⚠️")
    if st.session_state.telebot_mode == "Bật":
        try: 
            send_telegram_alert(f"🚨 CẢNH BÁO AN NINH!\nThời gian: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n⚠️ Cửa phòng đã mở liên tục quá 3 phút mà chưa được đóng lại!")
        except Exception: 
            pass
    clear_door_alert() # Dọn dẹp cờ cảnh báo trên Database sau khi xử lý xong

if isinstance(new_requests, dict) and new_requests:
    for req_id, req_data in new_requests.items():
        if isinstance(req_data, dict) and req_data.get("status") == "pending":
            img_url = req_data.get("image_url")
            del_url = req_data.get("delete_img_url", "")
            req_time = req_data.get("timestamp", int(time.time()))
            time_str = datetime.fromtimestamp(req_time).strftime("%Y-%m-%d %H:%M:%S") if isinstance(req_time, (int, float)) else str(req_time)

            if img_url:
                update_ai_status("pending") # Báo mạch kêu 1 bíp ngắn
                opencv_img, fetch_err = fetch_image_from_url(img_url)

                if opencv_img is not None:
                    has_samples = any(udata.get("samples") for udata in registered_db.values() if isinstance(udata, dict)) if isinstance(registered_db, dict) else False
                    log_id = f"log_{req_time}"

                    # TH1: CSDL Trống
                    if not has_samples:
                        update_ai_status("unknown") # CSDL trống -> Hú 5 tiếng
                        st.toast("🚨 CẢNH BÁO: CSDL trống! Không thể nhận diện (Người lạ)", icon="⚠️")
                        
                        add_history_log(log_id, {
                            "timestamp": time_str, "person_name": "Người lạ", 
                            "action": "Từ chối mở cửa (CSDL chưa có dữ liệu)", "image_url": img_url, "delete_img_url": del_url
                        })
                        if st.session_state.telebot_mode == "Bật":
                            try: send_telegram_alert(f"🚨 CẢNH BÁO NGƯỜI LẠ!\nThời gian: {time_str}\n⚠️ Kho dữ liệu CSDL hiện tại đang trống!\nẢnh: {img_url}")
                            except Exception: pass
                        delete_processed_request(req_id)
                        # LOẠI BỎ st.rerun() Ở ĐÂY ĐỂ TRÁNH GIÁN ĐOẠN UX
                        
                    # TH2: Có CSDL
                    else:
                        embedding, bbox, err = get_face_embedding(opencv_img)
                        if not err and embedding is not None:
                            best_name, min_dist, similarity, _ = find_best_match(embedding, registered_db)
                            
                            if "Người lạ" not in best_name:
                                update_ai_status("known") # Người quen -> Kêu 2 bíp, mở cửa
                                st.session_state.door_locked = False
                                st.toast(f"🔓 Đã mở cửa cho: {best_name} ({similarity:.1f}%)")
                                add_history_log(log_id, {
                                    "timestamp": time_str, "person_name": best_name, 
                                    "action": f"Mở cửa thành công ({similarity:.1f}%)", "image_url": img_url, "delete_img_url": del_url
                                })
                                delete_processed_request(req_id)
                            else:
                                update_ai_status("unknown") # Người lạ -> Hú 5 tiếng
                                st.toast("🚨 CẢNH BÁO: Phát hiện người lạ trước cửa!", icon="⚠️")
                                add_history_log(log_id, {
                                    "timestamp": time_str, "person_name": "Người lạ", 
                                    "action": "Từ chối mở cửa", "image_url": img_url, "delete_img_url": del_url
                                })
                                if st.session_state.telebot_mode == "Bật":
                                    try: send_telegram_alert(f"🚨 CẢNH BÁO NGƯỜI LẠ!\nThời gian: {time_str}\nPhát hiện người lạ trước cửa.\nẢnh: {img_url}")
                                    except Exception: pass
                                delete_processed_request(req_id)
                        
                        # BỔ SUNG ĐOẠN ELSE NÀY ĐỂ VÁ LỖI
                        else:
                            st.toast("⚠️ Ảnh lỗi hoặc không tìm thấy khuôn mặt, đã tự động hủy!", icon="🗑️")
                            delete_processed_request(req_id) # Bắt buộc phải chém bỏ request rác
                time.sleep(2) 
                update_ai_status("idle") # Trả hệ thống về trạng thái chờ

    

    
# --- DIỆN MẠO 1: TRANG ĐĂNG NHẬP ---
if not st.session_state.logged_in:
    # Căn giữa khung đăng nhập bằng cách chia cột
    col1, col2, col3 = st.columns([3, 2, 3])
    
    with col2:
        st.write("") # Tạo khoảng trống phía trên
        st.write("")
        st.markdown("<h2 style='text-align: center;'>ĐĂNG NHẬP HỆ THỐNG</h2>", unsafe_allow_html=True)
        
        # Form điền thông tin
        with st.form("login_form"):
            username = st.text_input("Tài khoản admin", placeholder="Nhập tên tài khoản...")
            password = st.text_input("Mật khẩu", type="password", placeholder="Nhập mật khẩu...")
            submit_button = st.form_submit_button("Đăng nhập", width='stretch')
            
            if submit_button:
                # Tạm thời cài tài khoản cố định để bạn dễ chạy thử test giao diện
                if username == "admin" and password == st.session_state.main_password:
                    st.session_state.logged_in = True
                    st.success("Đăng nhập thành công!")
                    st.rerun() # Khởi động lại trang để chuyển sang giao diện chính
                else:
                    st.error("Sai tài khoản hoặc mật khẩu! Vui lòng thử lại.")





# --- DIỆN MẠO 2: GIAO DIỆN CHÍNH (Sau khi đăng nhập thành công) ---
else:
    # Tạo thanh Sidebar bên cạnh để đặt nút Đăng xuất cho gọn   
    with st.sidebar:
        st.markdown("<h1 class='sidebar-title'>Cài đặt</h1>", unsafe_allow_html=True)
        st.markdown("<h1 class='sidebar-admin'>Tài khoản: Admin</h1>", unsafe_allow_html=True)

        if st.button("Thay đổi mật khẩu", type="primary", key="change-btn", width='stretch'):
            st.session_state.show_change_pw = not st.session_state.show_change_pw
            st.rerun() 

        if st.button("Đăng xuất", type="primary", key="logout-btn", width='stretch'):
            st.session_state.logged_in = False
            st.session_state.show_change_pw = False 
            st.rerun()

        st.write("---")
        st.markdown("### ⚙️ Hệ thống ngầm")
        # Công tắc bật/tắt quét tự động. Lưu vào session_state để nhớ trạng thái.
        st.session_state.auto_sync = st.toggle(
            "🔄 Quét khuôn mặt tự động", 
            value=True, 
            help="Tắt tạm thời khi bạn cần tải ảnh/nhập liệu để web không bị load lại giữa chừng."
        )

    # Nếu trạng thái show_change_pw là True, hiển thị Form nhập mật khẩu mới ngay bên dưới sidebar hoặc ở góc phù hợp
    if st.session_state.show_change_pw:
        with st.sidebar:
            st.write("---") # Đường kẻ phân chia
            with st.form("change_pw_form"):
                st.markdown("<h1 class='title-change-pw'>Đổi mật khẩu</h1>", unsafe_allow_html=True)
                old_pw = st.text_input("Mật khẩu cũ", type="password", placeholder="Nhập mật khẩu cũ...")
                new_pw = st.text_input("Mật khẩu mới", type="password", placeholder="Nhập mật khẩu mới...")
                confirm_pw = st.text_input("Xác nhận mật khẩu", type="password", placeholder="Nhập lại mật khẩu mới...")
                
                submit_change = st.form_submit_button("Xác nhận đổi", width='stretch')
                if submit_change:
                    # Kiểm tra logic đổi mật khẩu
                    if (old_pw == "" or new_pw == "" or confirm_pw == ""):
                        st.error("Vui lòng nhập đầy đủ các trường !!!")
                    elif new_pw != confirm_pw:
                        st.error("Mật khẩu mới không trùng khớp !!!")
                    elif old_pw != st.session_state.main_password: 
                        st.error("Mật khẩu cũ không chính xác !!!")
                    else:
                        st.session_state.main_password = new_pw
                        st.success("Đổi mật khẩu thành công !!!")
                        st.session_state.show_change_pw = False
                        st.rerun()




# Tiêu đề chính của Web Dashboard
    st.title("Hệ thống Cửa thông minh AIoT")
    st.write("---") 

    tab_control, tab_mock_esp, tab_history, tab_database = st.tabs([
        "📊 Bảng điều khiển", 
        "📷 Giả lập chụp ảnh ESP32", 
        "📜 Lịch sử ra vào", 
        "👥 Quản lý kho dữ liệu Face"
    ])



    # ----------------------------------------------------
    # TAB 1: BẢNG ĐIỀU KHIỂN TRUNG TÂM
    # ----------------------------------------------------
    with tab_control:
        st.markdown("<h2 style='text-align: left;'>📊 Hệ thống điều khiển thiết bị</h2>", unsafe_allow_html=True)
        st.write("")

        # Tự động cập nhật trạng thái đèn vật lý dựa trên Chế độ Đèn được chọn
        if st.session_state.light_mode == "Bật":
            st.session_state.light_on = True
        elif st.session_state.light_mode == "Tắt":
            st.session_state.light_on = False
        # Nếu là "Auto", trạng thái đèn sẽ do cảm biến quyết định (ở đây mặc định tạm thời là Tắt)
        elif st.session_state.light_mode == "Auto":
            st.session_state.light_on = False 

        # 2. CHIA BỐ CỤC LAYOUT THÀNH 2 CỘT: CỬA (TRÁI) & ĐÈN (PHẢI)
        col_door, col_light = st.columns(2, gap="large")

        # --- CỘT BÊN TRÁI: ĐIỀU KHIỂN CỬA RA VÀO VÀ PASS KEYPAD---
        with col_door:
            st.markdown("### 🚪 Quản lý Cửa ra vào")
            
            if st.session_state.door_locked:
                st.markdown(
                    """
                    <div style='background-color: #ffebe6; padding: 20px; border-radius: 10px; text-align: center; border-left: 6px solid #ff4d4f;'>
                        <h4 style='color: #ff4d4f; margin: 0; font-size: 18px;'>🔒 TRẠNG THÁI: CỬA ĐANG KHÓA</h4>
                        <p style='color: #666; margin: 5px 0 0 0; font-size: 13px;'>Hệ thống đang bảo vệ an toàn</p>
                    </div>
                    """, unsafe_allow_html=True
                )
                st.write("")
                if st.button("🔓 Click để mở cửa từ xa", type="primary", width='stretch'):
                    st.session_state.door_locked = False
                    remote_open_door()
                    st.toast("⚡ Lệnh mở cửa đã được gửi đến thiết bị!")
                    time.sleep(0.5)
                    st.rerun()
            else:
                st.markdown(
                    """
                    <div style='background-color: #e6f7ff; padding: 20px; border-radius: 10px; text-align: center; border-left: 6px solid #1890ff;'>
                        <h4 style='color: #1890ff; margin: 0; font-size: 18px;'>🔓 TRẠNG THÁI: CỬA ĐANG MỞ</h4>
                        <p style='color: #666; margin: 5px 0 0 0; font-size: 13px;'>Cửa đang mở, vui lòng chú ý</p>
                    </div>
                    """, unsafe_allow_html=True
                )
                st.write("")
                if st.button("🔒 Click để khóa cửa lại", type="secondary", width='stretch'):
                    st.session_state.door_locked = True
                    remote_lock_door()
                    st.toast("⚡ Lệnh khóa cửa đã được gửi đến thiết bị!")
                    time.sleep(0.5)
                    st.rerun()

            # ... Code hiển thị trạng thái nút Mở/Khóa cửa cũ
            st.write("---")
            st.markdown("### 🔑 Đổi mật khẩu cửa (Keypad)")
            with st.form("keypad_pw_form"):
                new_kp_pw = st.text_input("Mật khẩu Keypad mới:", type="password", placeholder="Nhập số (VD: 789)...")
                if st.form_submit_button("Cập nhật vào bộ nhớ mạch", width='stretch'):
                    if new_kp_pw:
                        change_keypad_password(new_kp_pw)
                        st.success(f"Đã gửi lệnh đổi mật khẩu cửa thành công!")
                    else:
                        st.error("Vui lòng không để trống mật khẩu!")

        # --- CỘT BÊN PHẢI: ĐIỀU KHIỂN ĐÈN HỆ THỐNG ---
        with col_light:
            st.markdown("### 💡 Hệ thống Đèn chiếu sáng")
            
            if st.session_state.light_on:
                st.markdown(
                    """
                    <div style='background-color: #fffbe6; padding: 20px; border-radius: 10px; text-align: center; border-left: 6px solid #faad14;'>
                        <h4 style='color: #faad14; margin: 0; font-size: 18px;'>💡 TRẠNG THÁI: ĐÈN ĐANG BẬT</h4>
                        <p style='color: #666; margin: 5px 0 0 0; font-size: 13px;'>Hệ thống đèn đang tiêu thụ điện năng</p>
                    </div>
                    """, unsafe_allow_html=True
                )
            else:
                st.markdown(
                    """
                    <div style='background-color: #f5f5f5; padding: 20px; border-radius: 10px; text-align: center; border-left: 6px solid #bfbfbf;'>
                        <h4 style='color: #595959; margin: 0; font-size: 18px;'>🌑 TRẠNG THÁI: ĐÈN ĐANG TẮT</h4>
                        <p style='color: #666; margin: 5px 0 0 0; font-size: 13px;'>Khu vực hiện tại không bật đèn</p>
                    </div>
                    """, unsafe_allow_html=True
                )
            
            st.write("")
            
            # Chọn chế độ hoạt động của đèn
            chosen_mode = st.segmented_control(
                "Thay đổi chế độ hoạt động của đèn:",
                options=["Bật", "Tắt", "Auto"],
                default=st.session_state.light_mode,
                key="light_mode_control"
            )
            
            # Cập nhật cấu hình khi người dùng đổi chế độ trên giao diện
            if chosen_mode and chosen_mode != st.session_state.light_mode:
                st.session_state.light_mode = chosen_mode
                update_light_mode(chosen_mode)
                st.toast(f"⚙️ Đã chuyển đèn sang chế độ: {chosen_mode}")
                time.sleep(0.3)
                st.rerun()

            # Chọn chế độ hoạt đông của telebot
            chosen_mode = st.segmented_control(
                "Bật thông báo thông qua telebot:",
                options=["Bật", "Tắt"],
                default=st.session_state.telebot_mode,
                key="telebot_control"
            )

            # Cập nhật khi đổi trạng thái telebot
            if chosen_mode != st.session_state.telebot_mode:
                st.session_state.telebot_mode = chosen_mode
                st.rerun()
        


    # ----------------------------------------------------
    # TAB 2: DEV TEST NEW REQ 
    # ----------------------------------------------------

    with tab_mock_esp:
        st.markdown("<h2 style='text-align: left;'>📷 Test gửi ảnh lên Firebase (Giả lập ESP32-CAM)</h2>", unsafe_allow_html=True)
        st.write("")
        
        esp_file = st.file_uploader("Tải ảnh quét khuôn mặt:", type=["jpg", "jpeg", "png"])
        
        if st.button("🚀 Mô phỏng gửi từ ESP32", type="primary"):
            if esp_file is not None:
                with st.spinner("Đang up ảnh lên ImgBB & gửi new req vào Firebase..."):
                    import base64
                    import requests
                    
                    # 1. API Gửi ảnh lên ImgBB
                    IMGBB_API_KEY = st.secrets["imgbb"]["api_key"]
                    encoded_img = base64.b64encode(esp_file.read()).decode('utf-8')
                    
                    payload = {
                        "key": IMGBB_API_KEY,
                        "image": encoded_img
                    }
                    res = requests.post("https://api.imgbb.com/1/upload", data=payload)
                    
                    if res.status_code == 200:
                        data = res.json()["data"]
                        img_url = data["url"]
                        delete_url = data["delete_url"]
                        img_time = data["time"] # Timestamp chuẩn UNIX từ ImgBB
                        
                        st.success(f"✅ Ảnh đã lên ImgBB: {img_url}")
                        st.image(img_url, width=250)
                        
                        # Truyền cả delete_url và img_time qua Firebase
                        from firebase_manager import push_esp32_mock_request
                        req_id = push_esp32_mock_request(img_url, delete_url, img_time)
                        
                        st.info(f"Đã tạo Request [{req_id}] trên Firebase.")
                    else:
                        st.error("Lỗi upload ImgBB!")
            else:
                st.warning("Bạn phải chọn ảnh trước!")



    # ----------------------------------------------------
    # TAB 3: LỊCH SỬ RA VÀO
    # ----------------------------------------------------
    with tab_history:
        st.markdown("<h2 style='text-align: left;'>Nhật ký quét khuôn mặt</h2>", unsafe_allow_html=True)
    

        # 1. GỌI HÀM LẤY DỮ LIỆU GIẢ TỪ FIREBASE MANAGER
        try:
            db_logs = get_history_logs()
        except Exception as e:
            st.error(f"Lỗi khi kết nối lấy dữ liệu: {e}")
            db_logs = {}

        # Nếu Firebase trả về None hoặc không phải dict -> Gán thành dict rỗng {}
        if not isinstance(db_logs, dict):
            db_logs = {}

        # 2. CHUYỂN ĐỔI DICTIONARY THÀNH LIST ĐỂ PANDAS ĐỌC ĐƯỢC
        formatted_logs = []
        for log_key, log_val in db_logs.items():
        
            formatted_logs.append({
                "ID":         log_key,
                "Thời gian":  log_val.get("timestamp", ""),
                "Nhân vật":  log_val.get("person_name", ""),
                "Trạng thái": log_val.get("action", ""),
                "Ảnh":        log_val.get("image_url", ""),
                "Delete_URL": log_val.get("delete_img_url", "")
            })
        df = pd.DataFrame(formatted_logs) # Tạo bảng Pandas DataFrame từ danh sách đã chuẩn hóa
        

        # 3. HIỂN THỊ RA GIAO DIỆN NẾU CÓ DỮ LIỆU
        if not df.empty:
            # Chỉ lấy các cột cần hiển thị trên bảng chính cho người dùng nhìn thấy
            view_df = df[["Thời gian", "Nhân vật", "Trạng thái"]]
            
            # CHIA BỐ CỤC: BẢNG BÊN TRÁI (70%), KHUNG ẢNH BÊN PHẢI (30%)
            col_table, col_preview = st.columns([7, 3], gap="large")
            
            with col_table:
                st.write("💡 *Nhấp chọn một dòng trong bảng dưới đây để xem ảnh chụp thực tế:*")
                
                # Tạo bảng tương tác cho phép chọn dòng
                selection = st.dataframe(
                    view_df,
                    width='stretch',
                    hide_index=True,
                    on_select="rerun",
                    selection_mode="single-row"
                )
                
            with col_preview:
                st.markdown("<h2 class='tab-2-preview-title'>Ảnh chụp camera</h2>", unsafe_allow_html=True)
                
                # Lấy thông tin dòng người dùng vừa click chọn  
                selected_rows = selection.get("selection", {}).get("rows", [])
                
                if selected_rows:
                    row_index = selected_rows[0]
                    selected_data = df.iloc[row_index]
                    
                    # Hiển thị thẻ thông tin tóm tắt bên dưới ảnh
                    st.info(f"""
                    **Thông tin chi tiết:**
                    * **Nhân vật:** {selected_data['Nhân vật']}
                    * **Thời gian:** {selected_data['Thời gian']}
                    * **Kết quả:**   {selected_data['Trạng thái']}
                    """)
                    
                    # XỬ LÝ ẢNH (Tự nhận diện link web hoặc file trong thư mục Face_History)
                    img_path_or_url = selected_data["Ảnh"]
                    
                    if img_path_or_url.startswith("http://") or img_path_or_url.startswith("https://"):
                        # Trường hợp 1: Nếu là link URL (Dữ liệu mock của bạn)
                        st.image(img_path_or_url, caption="Ảnh từ Database (URL)", width='stretch')
                    else:
                        # Trường hợp 2: Nếu là file local (Ví dụ: face_1.jpg)
                        local_path = img_path_or_url
                        if os.path.exists(local_path):
                            st.image(local_path, caption=f"Ảnh local: {img_path_or_url}", width='stretch')
                        else:
                            st.error(f"❌ Không tìm thấy file `{img_path_or_url}` trong thư mục `Face_History/`.")

                    # --- THÊM TÍNH NĂNG XÓA LOG & MỞ TAB XÓA ẢNH IMGBB ---
                    st.write("") # Tạo khoảng trống
                    if st.button("🗑️ Xóa nhật ký này", type="primary", width='stretch'):
                        with st.spinner("Đang dọn dẹp dữ liệu..."):
                            from firebase_manager import delete_history_log
                            
                            # 1. Xóa Log trên Firebase trước (Sạch dữ liệu hệ thống)
                            delete_history_log(selected_data["ID"])
                            if selected_data["Delete_URL"]:
                                open_urls_in_new_tabs(selected_data["Delete_URL"])
                                    
                            time.sleep(1.5)
                            st.rerun()

                else:
                    # Trạng thái ban đầu khi người dùng mới vào tab và chưa bấm chọn dòng nào
                    st.markdown(
                        """
                        <div class='tab-2-preview-box'>
                            <p class='tab-2-preview-box-p1'>Chưa có dòng nào được chọn.</p>
                            <p class='tab-2-preview-box-p2'>Vui lòng click vào một dòng bên bảng lịch sử để xem ảnh</p>
                        </div>
                        """, 
                        unsafe_allow_html=True
                    )
        else:
            st.warning("Hiện tại chưa có dữ liệu nhật ký nào trong hệ thống!")
        


    # ----------------------------------------------------
    # TAB 4: QUẢN LÝ KHO DỮ LIỆU FACE
    # ----------------------------------------------------
    with tab_database:
        st.markdown("<h2 style='text-align: left;'>Quản lý kho dữ liệu Face</h2>", unsafe_allow_html=True)
        
        registered_db, is_mock_db, JSON_PATH = load_registered_db()
        DB_DIR = "./source/Face_Database"

        # Hiển thị chế độ dữ liệu đang dùng
        if is_mock_db:
            st.caption("🟡 **Chế độ:** Local Mock (`registered_db.json`)")
        else:
            st.caption("🟢 **Chế độ:** Firebase Realtime Database (`/registered`)")
            

        # Chia giao diện thành 2 chức năng 
        db_action = st.segmented_control(
            "Chọn chức năng làm việc:", 
            options=["🔍 Kiểm tra nhận diện", "⚙️ Quản lý kho dữ liệu (Thêm / Xóa)"],
            default="🔍 Kiểm tra nhận diện",
            key="db_action_select"
        )
        st.write("---")
        

        # ====================================================
        # CHỨC NĂNG 1: KIỂM TRA DỮ LIỆU ẢNH (NHẬN DIỆN THỬ)
        # ====================================================
        if db_action == "🔍 Kiểm tra nhận diện":
            st.markdown("### 🔍 Test thử tính năng nhận diện khuôn mặt")
            st.write("Tải lên một bức ảnh bất kỳ để kiểm tra xem AI có nhận diện được là người quen hay không.")
            
            test_file = st.file_uploader("Chọn ảnh kiểm tra...", type=["jpg", "jpeg", "png"], key="test_face_upload")
            
            if test_file is not None:
                file_bytes = np.asarray(bytearray(test_file.read()), dtype=np.uint8)
                opencv_img = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
                opencv_img = cv2.cvtColor(opencv_img, cv2.COLOR_BGR2RGB)

                col_img, col_res = st.columns(2, gap="medium")
                with col_img:
                    st.image(test_file, caption="Ảnh đang kiểm tra", width='stretch')
                    
                with col_res:
                    st.markdown("#### ⚙️ Kết quả xử lý từ DeepFace:")
                    with st.spinner("Hệ thống AI đang trích xuất và đối sánh..."):
                        embedding, bbox, err = get_face_embedding(opencv_img)
                        
                        if err:
                            st.error(f"❌ {err}")
                        else:
                            best_name, min_dist, similarity, match_details = find_best_match(embedding, registered_db)
                            
                            m_col1, m_col2 = st.columns(2)
                            with m_col1:
                                st.metric(
                                    label="🎯 Độ tương đồng", 
                                    value=f"{similarity:.1f}%",
                                    delta="Đạt yêu cầu" if "Người lạ" not in best_name else "Dưới ngưỡng",
                                    delta_color="normal" if "Người lạ" not in best_name else "inverse"
                                )
                            with m_col2:
                                st.metric(
                                    label="📏 Khoảng cách Cosine", 
                                    value=f"{min_dist:.4f}",
                                    help="Khoảng cách càng nhỏ (gần 0) thì khuôn mặt càng giống nhau."
                                )

                            st.progress(int(similarity) / 100)

                            if "Người lạ" in best_name:
                                st.warning(f"🚨 Kết quả: **{best_name}** (Không khớp với ai trong CSDL)")
                            else:
                                st.success(f"✅ Xác thực thành công: **{best_name}**")

                            st.write("---")
                            
                            with st.expander("📊 Xem bảng khoảng cách chi tiết với từng người", expanded=True):
                                if match_details:
                                    df_details = pd.DataFrame(match_details)
                                    st.dataframe(df_details, width='stretch', hide_index=True)
                                else:
                                    st.info("Chưa có dữ liệu người quen trong CSDL.")


        # ====================================================
        # CHỨC NĂNG 2: THÊM VÀ XÓA DỮ LIỆU ẢNH
        # ====================================================
        elif db_action == "⚙️ Quản lý kho dữ liệu (Thêm / Xóa)":
            col_add, col_list = st.columns([4, 6], gap="large")
            
            # ----------------------------------------------------
            # CỘT TRÁI: FORM THÊM NGƯỜI MỚI HOẶC ẢNH MỚI
            # ----------------------------------------------------
            with col_add:
                st.markdown("### ➕ Cập nhật CSDL")
                
                valid_user_keys = [
                    uid for uid, udata in registered_db.items() 
                    if isinstance(udata, dict) and "name" in udata
                ]
                
                if not valid_user_keys:
                    st.info("💡 Chưa có dữ liệu thành viên. Vui lòng đăng ký người mới!")
                    add_mode = "Tạo người mới"
                else:
                    add_mode = st.radio(
                        "Chế độ:", 
                        ["Tạo người mới", "Thêm góc mặt cho người cũ"], 
                        horizontal=True
                    )
                
                target_uid = None
                reg_name = ""
                
                if add_mode == "Tạo người mới":
                    reg_name = st.text_input("Nhập họ và tên:", placeholder="Ví dụ: Nguyễn Văn A")
                    target_uid = f"user_{int(time.time())}"
                else:
                    target_uid = st.selectbox(
                        "Chọn người dùng cần thêm ảnh:",
                        options=valid_user_keys,
                        format_func=lambda x: f"{registered_db[x]['name']} ({len(registered_db[x].get('samples', {}))} ảnh)"
                    )
                    reg_name = registered_db[target_uid]["name"] if target_uid else ""

                reg_file = st.file_uploader("Tải ảnh chân dung rõ mặt:", type=["jpg", "jpeg", "png"], key="reg_face_upload")
                
                if st.button("Lưu vào hệ thống", type="primary", width='stretch'):
                    if not reg_name.strip():
                        st.error("Vui lòng nhập/chọn tên!")
                    elif reg_file is None:
                        st.error("Vui lòng tải ảnh lên!")
                    else:
                        file_bytes = np.asarray(bytearray(reg_file.read()), dtype=np.uint8)
                        opencv_img = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
                        opencv_img = cv2.cvtColor(opencv_img, cv2.COLOR_BGR2RGB)
                        
                        with st.spinner("AI đang quét khuôn mặt..."):
                            embedding, bbox, err = get_face_embedding(opencv_img)
                            
                            if err:
                                st.error(f"Thất bại: {err}")
                            else:
                                current_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                safe_filename = "".join([c for c in reg_name if c.isalnum() or c in (' ', '_', '-')]).strip()
                                sample_id = f"sample_{int(time.time())}"
                                
                                sample_data = {"embedding": embedding}

                                # NẾU LÀ LOCAL MOCK: Lưu file ảnh vào thư mục Face_Database
                                if is_mock_db:
                                    filename = f"{safe_filename}_{sample_id}.jpg"
                                    full_img_path = os.path.join(DB_DIR, filename)
                                    cv2.imwrite(full_img_path, cv2.cvtColor(opencv_img, cv2.COLOR_RGB2BGR))
                                    sample_data["image_path"] = filename
                                else:
                                    # NẾU LÀ FIREBASE: Upload ảnh lên ImgBB lấy URL online
                                    img_url, del_url = upload_to_imgbb(opencv_img)
                                    if img_url:
                                        sample_data["image_url"] = img_url
                                        sample_data["delete_img_url"] = del_url
                                    else:
                                        st.error("Không thể upload ảnh lên ImgBB, vui lòng thử lại!")
                                        st.stop()
                                
                                # Cập nhật cấu trúc dict
                                if target_uid not in registered_db or not isinstance(registered_db[target_uid], dict):
                                    registered_db[target_uid] = {"name": reg_name, "samples": {}}
                                
                                registered_db[target_uid]["updated_at"] = current_time_str
                                if "samples" not in registered_db[target_uid]:
                                    registered_db[target_uid]["samples"] = {}
                                    
                                registered_db[target_uid]["samples"][sample_id] = sample_data

                                # Đồng bộ lưu lại
                                save_registered_db(registered_db, is_mock_db, JSON_PATH)
                                    
                                st.success(f"🎉 Đã lưu thành công 1 góc mặt cho: {reg_name}")
                                time.sleep(1)
                                st.rerun()
                                
            # ----------------------------------------------------
            # CỘT PHẢI: XEM DANH SÁCH & BẤM VÀO ĐỂ HIỆN ẢNH XÓA
            # ----------------------------------------------------
            with col_list:
                st.markdown("### 📋 Kho ảnh đã đăng ký")
                
                list_data = []
                if isinstance(registered_db, dict):
                    for uid, user_info in registered_db.items():
                        if isinstance(user_info, dict):
                            for sid, sinfo in user_info.get("samples", {}).items():
                                if isinstance(sinfo, dict):
                                    list_data.append({
                                        "UID": uid,
                                        "Mã Ảnh (SID)": sid,
                                        "Tên thành viên": user_info.get("name", "N/A"),
                                        "Cập nhật lúc": user_info.get("updated_at", "Chưa rõ"),
                                        "Tên file ảnh": sinfo.get("image_path", ""),
                                        "URL Ảnh": sinfo.get("image_url", ""),
                                        "URL Xóa Ảnh": sinfo.get("delete_img_url", "")
                                    })
                
                if not list_data:
                    st.info("Hiện tại kho dữ liệu đang trống.")
                else:
                    df_db = pd.DataFrame(list_data)
                    view_df = df_db[["Tên thành viên", "Mã Ảnh (SID)", "Cập nhật lúc"]]
                    
                    st.write("💡 *Nhấp chọn một dòng để xem ảnh và thao tác xóa:*")
                    selection = st.dataframe(
                        view_df, 
                        width='stretch', 
                        hide_index=True,
                        on_select="rerun",
                        selection_mode="single-row"
                    )
                    
                    selected_rows = selection.get("selection", {}).get("rows", [])
                    if selected_rows:
                        row_index = selected_rows[0]
                        selected_data = df_db.iloc[row_index]
                        
                        del_uid = selected_data["UID"]
                        del_sid = selected_data["Mã Ảnh (SID)"]
                        del_filename = selected_data["Tên file ảnh"]
                        del_url = selected_data["URL Ảnh"]
                        del_imgbb_url = selected_data["URL Xóa Ảnh"]
                        del_name = selected_data["Tên thành viên"]
                        
                        st.markdown("---")
                        col_img_preview, col_action = st.columns([1, 1], gap="medium")
                        
                        # HIỂN THỊ ẢNH
                        with col_img_preview:
                            if del_url and del_url.startswith("http"):
                                st.image(del_url, caption=f"Mẫu: {del_sid}", width='stretch')
                            elif del_filename:
                                img_path = os.path.join(DB_DIR, del_filename)
                                if os.path.exists(img_path):
                                    st.image(img_path, caption=f"Mẫu: {del_sid}", width='stretch')
                                else:
                                    st.error(f"Không tìm thấy file ảnh: {del_filename}")
                            else:
                                st.warning("Không có hình ảnh hiển thị.")
                                
                        # CÁC NÚT XÓA
                        with col_action:
                            st.markdown(f"**Nhân vật:** {del_name}")
                            st.write("")
                            
                            # XÓA 1 ẢNH
                            if st.button("🗑️ Chỉ xóa ảnh này", type="primary", width='stretch'):
                                # import streamlit.components.v1 as components
                                
                                # Xóa file local nếu có
                                if del_filename:
                                    p = os.path.join(DB_DIR, del_filename)
                                    if os.path.exists(p): os.remove(p)
                                
                                # Nếu có link hủy ImgBB -> Bật tab mới cho người dùng bấm xóa
                                if del_imgbb_url and del_imgbb_url.startswith("http"):
                                    open_urls_in_new_tabs(del_imgbb_url)
                                
                                if del_sid in registered_db[del_uid]["samples"]:
                                    del registered_db[del_uid]["samples"][del_sid]
                                
                                if not registered_db[del_uid]["samples"]:
                                    del registered_db[del_uid]
                                
                                save_registered_db(registered_db, is_mock_db, JSON_PATH)
                                st.success("Đã xóa dữ liệu thành công!")
                                time.sleep(1.5)
                                st.rerun()
                                
                            st.write("")
                            
                            # XÓA TOÀN BỘ NGƯỜI
                            if st.button("🚨 Xóa toàn bộ người này", type="secondary", width='stretch'):
                                import streamlit.components.v1 as components
                                
                                del_urls = []
                                # 1. Duyệt qua tất cả ảnh mẫu của người này
                                for sid, sinfo in registered_db[del_uid].get("samples", {}).items():
                                    # Xóa file vật lý local (nếu chạy mode Local)
                                    f_name = sinfo.get("image_path")
                                    if f_name:
                                        p = os.path.join(DB_DIR, f_name)
                                        if os.path.exists(p): 
                                            os.remove(p)
                                            
                                    # Gom link xóa ImgBB (nếu chạy mode Firebase)
                                    d_url = sinfo.get("delete_img_url")
                                    if d_url and d_url.startswith("http"):
                                        del_urls.append(d_url)
                                
                                # 2. Bật Tab mới cho tất cả các link xóa ảnh ImgBB của người này
                                if del_urls:
                                    open_urls_in_new_tabs(del_urls)
                                
                                # 3. Xóa hoàn toàn user khỏi Database
                                del registered_db[del_uid]
                                save_registered_db(registered_db, is_mock_db, JSON_PATH)
                                
                                st.success(f"🎉 Đã xóa toàn bộ hồ sơ của {del_name}!")
                                time.sleep(1.5)
                                st.rerun()