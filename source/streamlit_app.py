import streamlit as st
import pandas as pd
from datetime import datetime
import cv2
import numpy as np
from streamlit_autorefresh import st_autorefresh

# Cấu hình của firebase (sẽ config sau)
from firebase_manager import (init_firebase, get_new_requests, get_history_logs, update_request_status, add_history_log, get_registered_faces, register_new_face)

# Cấu hình của model nhận diện khuôn mắt (sẽ config sau)
from face_engine import (fetch_image_from_url, get_face_embedding, find_best_match)



# Mục tiêu đề cho Website
st.set_page_config(page_title="Hệ thống Cửa thông minh AIoT", layout="wide")

# Đọc file css
with open("source/style.css", "r", encoding="utf-8") as f:
    custom_css = f.read()

st.markdown(f"<style>{custom_css}</style>", unsafe_allow_html=True)



# Các biến lưu trong server data
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if "show_change_pw" not in st.session_state:
    st.session_state.show_change_pw = False

if "main_password" not in st.session_state:
    st.session_state.main_password = "123456"




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
            submit_button = st.form_submit_button("Đăng nhập", use_container_width=True)
            
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

        if st.button("Thay đổi mật khẩu", type="primary", key="change-btn", use_container_width=True):
            st.session_state.show_change_pw = not st.session_state.show_change_pw
            st.rerun() 

        if st.button("Đăng xuất", type="primary", key="logout-btn", use_container_width=True):
            st.session_state.logged_in = False
            st.session_state.show_change_pw = False 
            st.rerun()

    # Nếu trạng thái show_change_pw là True, hiển thị Form nhập mật khẩu mới ngay bên dưới sidebar hoặc ở góc phù hợp
    if st.session_state.show_change_pw:
        with st.sidebar:
            st.write("---") # Đường kẻ phân chia
            with st.form("change_pw_form"):
                st.markdown("<h1 class='title-change-pw'>Đổi mật khẩu</h1>", unsafe_allow_html=True)
                old_pw = st.text_input("Mật khẩu cũ", type="password", placeholder="Nhập mật khẩu cũ...")
                new_pw = st.text_input("Mật khẩu mới", type="password", placeholder="Nhập mật khẩu mới...")
                confirm_pw = st.text_input("Xác nhận mật khẩu", type="password", placeholder="Nhập lại mật khẩu mới...")
                
                submit_change = st.form_submit_button("Xác nhận đổi", use_container_width=True)
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
    st.write("---") # Đường gạch ngang phân chia

    # Khởi tạo 3 Tabs theo đúng ý tưởng mới của bạn
    tab_control, tab_history, tab_database = st.tabs([
        "📊 Bảng điều khiển trung tâm", 
        "📜 Lịch sử ra vào", 
        "👥 Quản lý kho dữ liệu Face"
    ])
    
    # ----------------------------------------------------
    # TAB 1: BẢNG ĐIỀU KHIỂN TRUNG TÂM
    # ----------------------------------------------------
    with tab_control:
        st.subheader("Trạng thái thiết bị & Nút điều khiển nhanh")
        # Gợi ý thiết kế của bạn: Đặt các nút bấm mở cửa thủ công, xem camera live, hoặc thông số pin/kết nối của ESP32-CAM tại đây.
        
    # ----------------------------------------------------
    # TAB 2: LỊCH SỬ RA VÀO
    # ----------------------------------------------------
    with tab_history:
        st.subheader("Nhật ký quét khuôn mặt ra vào")
        # Gợi ý thiết kế của bạn: Hiển thị bảng tra cứu lịch sử, bộ lọc tìm kiếm theo tên hoặc theo ngày tháng.

    # ----------------------------------------------------
    # TAB 3: QUẢN LÝ KHO DỮ LIỆU FACE
    # ----------------------------------------------------
    with tab_database:
        st.subheader("Danh sách thành viên & Đăng ký người mới")
        # Gợi ý thiết kế của bạn: Chia làm 2 cột. Một bên là form tải ảnh đăng ký khuôn mặt mới, một bên là danh sách/bảng những người hiện có kèm nút "Xóa" nếu muốn hủy quyền ra vào của họ.
