import streamlit as st
import pandas as pd
from datetime import datetime
import time
import json
import os
import cv2
import numpy as np
from streamlit_autorefresh import st_autorefresh

# Cấu hình của firebase (sẽ config sau)
from firebase_manager import (init_firebase, get_new_requests, get_history_logs, update_request_status, add_history_log, get_registered_faces, register_new_face)

# Cấu hình của model nhận diện khuôn mắt (sẽ config sau)
from face_engine import (fetch_image_from_url, get_face_embedding, find_best_match, warmup_ai_model)
warmup_ai_model() # Gọi hàm khởi động ngầm ngay khi app Streamlit vừa bật lên



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
    st.write("---") # Đường gạch ngang phân chia

    # Khởi tạo 3 Tabs theo đúng ý tưởng mới của bạn
    tab_control, tab_history, tab_database = st.tabs([
        "📊 Bảng điều khiển trung tâm", 
        "📜 Lịch sử ra vào", 
        "👥 Quản lý kho dữ liệu Face"
    ],  key='Tab-Selection')
    
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
        st.markdown("<h2 style='text-align: left;'>Nhật ký quét khuôn mặt</h2>", unsafe_allow_html=True)
    

        # 1. GỌI HÀM LẤY DỮ LIỆU GIẢ TỪ FIREBASE MANAGER
        try:
            db_logs = get_history_logs()
        except Exception as e:
            st.error(f"Lỗi khi kết nối lấy dữ liệu: {e}")
            db_logs = {}


        # 2. CHUYỂN ĐỔI DICTIONARY THÀNH LIST ĐỂ PANDAS ĐỌC ĐƯỢC
        formatted_logs = []
        for log_key, log_val in db_logs.items():
        
            formatted_logs.append({
                "ID":         log_key,
                "Thời gian":  log_val.get("timestamp", ""),
                "Đối tượng":  log_val.get("person_name", ""),
                "Trạng thái": log_val.get("action", ""),
                "Ảnh":        log_val.get("image_url", "")
            })
        df = pd.DataFrame(formatted_logs) # Tạo bảng Pandas DataFrame từ danh sách đã chuẩn hóa
        

        # 3. HIỂN THỊ RA GIAO DIỆN NẾU CÓ DỮ LIỆU
        if not df.empty:
            # Chỉ lấy các cột cần hiển thị trên bảng chính cho người dùng nhìn thấy
            view_df = df[["Thời gian", "Đối tượng", "Trạng thái"]]
            
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
                    * **Đối tượng:** {selected_data['Đối tượng']}
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
    # TAB 3: QUẢN LÝ KHO DỮ LIỆU FACE
    # ----------------------------------------------------
    with tab_database:
        st.markdown("<h2 style='text-align: left;'>Quản lý kho dữ liệu Face</h2>", unsafe_allow_html=True)
        
        # 1. CẤU HÌNH THƯ MỤC LƯU TRỮ LOCAL
        DB_DIR = "./source/Face_Database"
        JSON_PATH = os.path.join(DB_DIR, "registered_db.json")
        os.makedirs(DB_DIR, exist_ok=True) # Tự động tạo thư mục Face_Database nếu chưa có
        

        # Tải dữ liệu bộ nhớ đặc trưng từ file JSON local lên hệ thống
        if os.path.exists(JSON_PATH):
            with open(JSON_PATH, "r", encoding="utf-8") as f:
                registered_db = json.load(f)
        else:
            registered_db = {}
            

        # 2. CHIA GIAO DIỆN THÀNH 2 PHÂN VÙNG CHỨC NĂNG LỚN
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
                # Chuyển đổi dữ liệu ảnh tải lên thành ma trận OpenCV
                file_bytes = np.asarray(bytearray(test_file.read()), dtype=np.uint8)
                opencv_img = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
                
                col_img, col_res = st.columns(2, gap="medium")
                with col_img:
                    st.image(test_file, caption="Ảnh đang kiểm tra", width='stretch')
                    
                with col_res:
                    st.markdown("#### ⚙️ Kết quả xử lý từ DeepFace:")
                    with st.spinner("Hệ thống AI đang trích xuất và đối sánh..."):
                        # Gọi hàm trích xuất của bạn
                        embedding, bbox, err = get_face_embedding(opencv_img)
                        
                        if err:
                            st.error(f"❌ {err}")
                        else:
                            # Gọi hàm đối sánh Cosine Distance của bạn
                            name_result = find_best_match(embedding, registered_db)
                            
                            if "Người lạ" in name_result:
                                st.warning(f"🚨 Hệ thống cảnh báo: **{name_result}**")
                            else:
                                st.success(f"✅ Xác thực thành công: **{name_result}**")


        # ====================================================
        # CHỨC NĂNG 2: THÊM VÀ XÓA DỮ LIỆU ẢNH
        # ====================================================
        elif db_action == "⚙️ Quản lý kho dữ liệu (Thêm / Xóa)":
            col_add, col_list = st.columns([4, 6], gap="large")
            
            # --- PHẦN THÊM DỮ LIỆU MỚI ---
            with col_add:
                st.markdown("### ➕ Thêm người mới")
                reg_name = st.text_input("Nhập họ và tên người đăng ký:", placeholder="Ví dụ: Nguyễn Văn A")
                reg_file = st.file_uploader("Tải ảnh chân dung rõ mặt:", type=["jpg", "jpeg", "png"], key="reg_face_upload")
                
                if st.button("Đăng ký vào hệ thống", type="primary", width='stretch'):
                    if not reg_name.strip():
                        st.error("Vui lòng không để trống tên người đăng ký!")
                    elif reg_file is None:
                        st.error("Vui lòng tải ảnh chân dung lên!")
                    else:
                        # Đọc ảnh sang định dạng OpenCV
                        file_bytes = np.asarray(bytearray(reg_file.read()), dtype=np.uint8)
                        opencv_img = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
                        
                        with st.spinner("AI đang quét khuôn mặt mẫu..."):
                            embedding, bbox, err = get_face_embedding(opencv_img)
                            
                            if err:
                                st.error(f"Đăng ký thất bại: {err}")
                            else:
                                # Loại bỏ ký tự đặc biệt trong tên để đặt tên file an toàn
                                safe_filename = "".join([c for c in reg_name if c.isalnum() or c in (' ', '_', '-')]).strip()
                                filename = f"{safe_filename}_{int(time.time())}.jpg"
                                full_img_path = os.path.join(DB_DIR, filename)
                                
                                # 1. Lưu file ảnh vật lý vào thư mục local Face_Database
                                cv2.imwrite(full_img_path, opencv_img)
                                
                                # 2. Cập nhật dữ liệu Vector vào dictionary
                                uid = f"user_{int(time.time())}"
                                registered_db[uid] = {
                                    "name": reg_name,
                                    "embedding": embedding,
                                    "image_path": filename
                                }
                                
                                # 3. Ghi đè cập nhật lại file JSON local
                                with open(JSON_PATH, "w", encoding="utf-8") as f:
                                    json.dump(registered_db, f, ensure_ascii=False, indent=4)
                                    
                                st.success(f"🎉 Đã đăng ký thành công gương mặt cho: {reg_name}")
                                time.sleep(1)
                                st.rerun()
                                
            # --- PHẦN DANH SÁCH & XÓA DỮ LIỆU ---
            with col_list:
                st.markdown("### 📋 Danh sách người quen đã đăng ký")
                
                if not registered_db:
                    st.info("Hiện tại kho dữ liệu local đang trống.")
                else:
                    # Chuyển đổi sang bảng DataFrame để hiển thị danh sách trực quan
                    list_data = []
                    for uid, data in registered_db.items():
                        list_data.append({
                            "Mã định danh": uid,
                            "Tên thành viên": data.get("name"),
                            "Tên file ảnh": data.get("image_path")
                        })
                    df_db = pd.DataFrame(list_data)
                    st.dataframe(df_db[["Tên thành viên", "Tên file ảnh"]], width='stretch', hide_index=True)
                    
                    st.markdown("---")
                    st.markdown("### 🗑️ Xóa thành viên khỏi hệ thống")
                    
                    # Hộp chọn đối tượng cần xóa
                    delete_uid = st.selectbox(
                        "Chọn người muốn xóa dữ liệu:",
                        options=list(registered_db.keys()),
                        format_func=lambda x: registered_db[x]["name"]
                    )
                    
                    if st.button("Xác nhận xóa hoàn toàn", type="secondary", width='stretch'):
                        # 1. Tìm và xóa file ảnh vật lý trong thư mục Face_Database trên ổ cứng
                        file_to_delete = registered_db[delete_uid].get("image_path")
                        if file_to_delete:
                            full_del_path = os.path.join(DB_DIR, file_to_delete)
                            if os.path.exists(full_del_path):
                                os.remove(full_del_path)
                                
                        # 2. Xóa thông tin và Vector trong cấu hình Dictionary
                        del registered_db[delete_uid]
                        
                        # 3. Lưu lại file JSON sau khi xóa
                        with open(JSON_PATH, "w", encoding="utf-8") as f:
                            json.dump(registered_db, f, ensure_ascii=False, indent=4)
                            
                        st.success("Đã xóa bỏ dữ liệu thành công!")
                        time.sleep(1)
                        st.rerun()
