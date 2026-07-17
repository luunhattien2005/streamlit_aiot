import requests
import streamlit as st
import cv2
import numpy as np
from deepface import DeepFace

def fetch_image_from_url(url):
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
    try:
        ### Lấy representation (vector) thay vì tự so sánh
        #Mô hình VGG-Face
        res = DeepFace.represent(
            img_path=img, 
            model_name="VGG-Face", 
            enforce_detection=True,
            detector_backend="opencv"
        )

        # Mô hình Facenet
        # res = DeepFace.represent(
        #     img_path=img, 
        #     model_name="Facenet", 
        #     enforce_detection=True,
        #     detector_backend="opencv"
        # )

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
    """Tính toán khoảng cách Cosine chuẩn chỉnh"""
    a = np.array(source_emb)
    b = np.array(test_emb)
    return 1 - np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))



def find_best_match(target_embedding, registered_db):
    """So sánh Vector lấy được với Database đã đăng ký"""
    if not registered_db:
        return "Người lạ (Chưa có ai đăng ký)"
    
    best_match_name = "Người lạ"
    min_distance = float("inf")
    # Ngưỡng (Threshold) chuẩn của model VGG-Face dùng Cosine là 0.68
    VGG_FACE_THRESHOLD = 0.68 
    FACENET_THRESHOLD  = 0.40

    for uid, data in registered_db.items():
        db_embedding = data.get("embedding")
        db_name = data.get("name")
        
        if db_embedding:
            distance = calculate_cosine_distance(target_embedding, db_embedding)
            if distance < min_distance:
                min_distance = distance
                if distance < VGG_FACE_THRESHOLD:
                    best_match_name = db_name
                    
    return best_match_name



@st.cache_resource
def warmup_ai_model():
    """Chạy ngầm để nạp sẵn mô hình VGG-Face vào RAM ngay khi mở Web"""
    # Tạo một ảnh đen giả lập kích thước 224x224 để "mồi" cho AI
    dummy_img = np.zeros((224, 224, 3), dtype=np.uint8)
    # Ép DeepFace chạy trước một lần, bỏ qua bước check khuôn mặt thật
    try:
        #Mô hình VGG-Face
        DeepFace.represent(
            img_path=dummy_img, 
            model_name="VGG-Face", 
            enforce_detection=True,
            detector_backend="opencv"
        )

        # Mô hình Facenet
        # DeepFace.represent(
        #     img_path=dummy_img, 
        #     model_name="Facenet", 
        #     enforce_detection=True,
        #     detector_backend="opencv"
        # )
    except Exception:
        pass