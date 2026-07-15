import streamlit as st
import pandas as pd
from datetime import datetime
import cv2
import numpy as np
from streamlit_autorefresh import st_autorefresh

from firebase_manager import (init_firebase, get_new_requests, get_history_logs, 
                              update_request_status, add_history_log, get_registered_faces, register_new_face)
from face_engine import fetch_image_from_url, get_face_embedding, find_best_match

st.set_page_config(page_title="Smart Door Dashboard", layout="wide")
st.title("🚪 Hệ thống Cửa thông minh AIoT")

with st.spinner("Đang kết nối hệ thống..."):
    is_connected, msg = init_firebase()

if not is_connected:
    st.error("Hệ thống đang tạm gián đoạn. Không thể kết nối cơ sở dữ liệu.")
    st.error(f"Chi tiết kỹ thuật: {msg}")
    st.stop()

# Chia làm 3 Tabs
tab_engine, tab_dashboard, tab_register = st.tabs(["⚙️ Lắng Nghe Mở Cửa", "📊 Lịch Sử Ra Vào", "👤 Đăng ký Khuôn Mặt"])

# --- TAB 1: ENGINE ---
with tab_engine:
    count = st_autorefresh(interval=2000, limit=20000, key="fbreq")
    st.write(f"Trạng thái: Đang trực quét... (Ping: {count})")
    
    requests_data = get_new_requests()
    if requests_data:
        for req_id, req_data in requests_data.items():
            if req_data.get('status') == 'pending':
                st.info(f"🔔 Phát hiện yêu cầu mới: {req_id}")
                img_url = req_data.get('image_url', '')
                img_data, err_msg = fetch_image_from_url(img_url)
                
                if img_data is not None:
                    with st.spinner("AI đang phân tích khuôn mặt..."):
                        # 1. Lấy vector khuôn mặt
                        target_emb, bbox, ai_err = get_face_embedding(img_data)
                        
                        person_name = "Lỗi nhận diện"
                        if target_emb:
                            # 2. Tải database người nhà từ Firebase
                            registered_db = get_registered_faces()
                            # 3. Quét Brute Force tìm người giống nhất
                            person_name = find_best_match(target_emb, registered_db)
                        elif ai_err:
                            person_name = "Người lạ (Không thấy rõ mặt)"
                    
                    action_text = "Mở cửa thành công" if "Người lạ" not in person_name and "Lỗi" not in person_name else "Từ chối mở cửa"
                    
                    add_history_log({
                        'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        'image_url': img_url,
                        'person_name': person_name,
                        'action': action_text,
                        'bbox': bbox if bbox else {}
                    })
                    update_request_status(req_id, 'completed')
                    st.success(f"✅ Đã xử lý: {person_name} | {action_text}")
                else:
                    st.error(err_msg)
    else:
        st.write("Không có yêu cầu mở cửa nào mới.")

# --- TAB 2: DASHBOARD ---
with tab_dashboard:
    logs_data = get_history_logs()
    if logs_data:
        logs_list = [{'log_id': k, **v} for k, v in logs_data.items()]
        df = pd.DataFrame(logs_list)
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df = df.sort_values(by='timestamp', ascending=False).reset_index(drop=True)
        st.dataframe(df[['timestamp', 'person_name', 'action']], use_container_width=True)
    else:
        st.info("Chưa có dữ liệu.")

# --- TAB 3: ĐĂNG KÝ KHUÔN MẶT MỚI ---
with tab_register:
    st.markdown("### Thêm người dùng vào hệ thống (Nhiều góc mặt càng tốt)")
    new_name = st.text_input("Nhập tên người dùng (VD: Tiến Lưu):")
    uploaded_file = st.file_uploader("Tải ảnh khuôn mặt (Ảnh tự chụp điện thoại)", type=["jpg", "jpeg", "png"])
    
    if st.button("Đăng ký vào Database", type="primary"):
        if not new_name.strip():
            st.warning("Vui lòng nhập tên người dùng!")
        elif uploaded_file is None:
            st.warning("Vui lòng tải ảnh lên!")
        else:
            with st.spinner("Đang trích xuất Vector đặc trưng (Embedding)..."):
                # Đọc ảnh từ file tải lên
                file_bytes = np.asarray(bytearray(uploaded_file.read()), dtype=np.uint8)
                img_to_register = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
                
                # Trích xuất Vector
                embedding, _, err = get_face_embedding(img_to_register)
                
                if embedding:
                    # Đẩy vector lên Firebase
                    register_new_face(new_name.strip(), embedding)
                    st.success(f"🎉 Đã đăng ký thành công Vector cho '{new_name}'!")
                    st.image(cv2.cvtColor(img_to_register, cv2.COLOR_BGR2RGB), width=200, caption="Khuôn mặt đã lưu")
                else:
                    st.error(f"❌ Đăng ký thất bại: {err}")