import time
from firebase_admin import db
from firebase_manager import is_mock

def send_firebase_command(node, value):
    """Ghi lệnh kèm timestamp xuống Firebase để ép mạch nhận diện sự thay đổi"""
    if not is_mock("mock_database"):
        try:
            payload = {
                "value": value,
                "timestamp": int(time.time())
            }
            db.reference(f'device_control/{node}').set(payload)
        except Exception as e:
            print(f"Lỗi khi gửi lệnh Firebase ({node}): {e}")

def update_ai_status(status):
    """Trạng thái AI: 'pending', 'known', 'unknown', 'idle'"""
    send_firebase_command('ai_status', status)

def remote_open_door():
    """Lệnh mở cửa từ xa"""
    send_firebase_command('door', 'open')
    
def remote_lock_door():
    """Lệnh khóa cửa từ xa"""
    send_firebase_command('door', 'close')

def update_light_mode(mode):
    """Đổi chế độ đèn: 'on', 'off', 'auto'"""
    mode_map = {"Bật": "on", "Tắt": "off", "Auto": "auto"}
    command = mode_map.get(mode, "auto")
    send_firebase_command('light', command)

def change_keypad_password(new_password):
    """Cập nhật mật khẩu Keypad"""
    send_firebase_command('new_password', new_password)