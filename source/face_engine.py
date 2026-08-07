import requests
import streamlit as st
import cv2
import numpy as np
from deepface import DeepFace

VGG_FACE_THRESHOLD = 0.40 
FACENET_THRESHOLD  = 0.33

def fetch_image_from_url(url):
    """Tải ảnh từ URL và trả về ảnh OpenCV"""
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        img_array = np.asarray(bytearray(response.content), dtype=np.uint8)
        img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        return img, None
    except Exception as e:
        return None, f"Lỗi tải ảnh: {str(e)}"



def get_face_embedding(img):
    """Trích xuất mảng vector đặc trưng và tọa độ khuôn mặt"""
    if img is None or img.size == 0:
        return None, None, "Ảnh tải lên không hợp lệ hoặc bị rỗng!"
    try:
        # Mô hình Facenet512
        res = DeepFace.represent(
            img_path=img, 
            model_name="Facenet512", 
            enforce_detection=True,
            detector_backend="ssd" # ssd
        )

        if len(res) > 0:
            embedding = res[0]["embedding"]
            bbox =      res[0]["facial_area"]
            return embedding, bbox, None
    except ValueError:
        return None, None, "Không phát hiện thấy khuôn mặt trong ảnh"
    except Exception as e:
        return None, None, f"Lỗi AI: {str(e)}"
    return None, None, "Lỗi không xác định"



def calculate_cosine_distance(source_emb, test_emb):
    """Tính toán khoảng cách Cosine"""
    a = np.array(source_emb)
    b = np.array(test_emb)
    return 1 - np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

def find_best_match(target_embedding, registered_db):
    """
    So sánh Vector lấy được với Database (Cấu trúc mới: 1 người có nhiều samples).
    Trả về: (best_match_name, min_distance, max_similarity, match_details)
    """
    if not registered_db:
        return "Người lạ (Chưa có dữ liệu)", 1.0, 0.0, []
    
    best_match_name = "Người lạ"
    min_distance = float("inf")

    match_details = []

    # Lặp qua từng người dùng
    for uid, user_data in registered_db.items():
        db_name = user_data.get("name", "Không tên")
        samples = user_data.get("samples", {})
        
        # Lặp qua từng mẫu ảnh của người đó
        for sample_id, sample_data in samples.items():
            db_embedding = sample_data.get("embedding")
            
            if db_embedding is not None:
                distance = calculate_cosine_distance(target_embedding, db_embedding)
                similarity = max(0.0, min(100.0, (1.0 - distance) * 100))
                
                match_details.append({
                    "Tên thành viên": f"{db_name} ({sample_id})", # Hiển thị rõ tên khớp với góc ảnh nào
                    "Khoảng cách Cosine": round(float(distance), 4),
                    "Độ tương đồng (%)": round(float(similarity), 2)
                })
                
                # Nếu khoảng cách này là nhỏ nhất từ trước tới giờ
                if distance < min_distance:
                    min_distance = distance
                    # Nếu vượt qua ngưỡng tin cậy của face recognition, thì coi là khớp với người đó
                    if distance < FACENET_THRESHOLD:
                        best_match_name = db_name # Vẫn trả về tên gốc để mở cửa

    match_details = sorted(match_details, key=lambda x: x["Khoảng cách Cosine"])
    best_similarity = max(0.0, min(100.0, (1.0 - min_distance) * 100)) if min_distance != float("inf") else 0.0

    return best_match_name, min_distance, best_similarity, match_details


@st.cache_resource
def warmup_ai_model():
    """Chạy ngầm để nạp sẵn mô hình VGG-Face vào RAM ngay khi mở Web"""
    # Tạo một ảnh đen giả lập kích thước 224x224 để "mồi" cho AI
    dummy_img = np.zeros((224, 224, 3), dtype=np.uint8)
    # Ép DeepFace chạy trước một lần, bỏ qua bước check khuôn mặt thật
    try:
        # Mô hình Facenet512
        DeepFace.represent(
            img_path=dummy_img, 
            model_name="Facenet512", 
            enforce_detection=True,
            detector_backend="ssd" # ssd
        )
    except Exception:
        pass