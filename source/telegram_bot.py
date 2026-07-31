import requests
import streamlit as st
import logging

def send_telegram_alert(message, image_url=None):
    """
    Gửi cảnh báo tới Telegram. Dùng credentials từ Streamlit secrets.
    - Nếu có image_url -> gửi kèm ảnh (sendPhoto).
    - Nếu KHÔNG có image_url (vd: cảnh báo cửa mở quá lâu, không có ảnh chụp)
      -> gửi tin nhắn văn bản thuần (sendMessage) thay vì bắt buộc phải có ảnh.
    """
    try:
        # Check if secrets are configured
        if "telegram" not in st.secrets:
            logging.warning("Telegram secrets not found in .streamlit/secrets.toml")
            st.toast("⚠️ Không thể gửi cảnh báo Telegram (Thiếu cấu hình bot_token/chat_id)")
            return False
            
        bot_token = st.secrets["telegram"].get("bot_token")
        chat_id = st.secrets["telegram"].get("chat_id")
        
        if not bot_token or not chat_id:
            logging.warning("Telegram token or chat_id is missing.")
            st.toast("⚠️ Không thể gửi cảnh báo Telegram (Cấu hình không đầy đủ)")
            return False

        if image_url:
            # Có ảnh -> gửi kèm ảnh
            api_url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
            payload = {
                "chat_id": chat_id,
                "photo": image_url,
                "caption": message,
                "parse_mode": "Markdown"
            }
        else:
            # Không có ảnh (vd: cảnh báo cửa mở quá 3 phút) -> gửi tin nhắn text thuần
            api_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            payload = {
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "Markdown"
            }
        
        # Send request
        response = requests.post(api_url, data=payload)
        
        if response.status_code == 200:
            return True
        else:
            logging.error(f"Telegram API Error: {response.text}")
            st.toast(f"❌ Lỗi API Telegram: {response.status_code}")
            return False
            
    except Exception as e:
        logging.error(f"Error sending Telegram alert: {e}")
        return False