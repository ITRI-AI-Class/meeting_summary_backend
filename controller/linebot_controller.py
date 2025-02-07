from flask import Blueprint, request, jsonify
import requests
import uuid

import firebase_admin
from firebase_admin import firestore

# 🔹 只取得 `db`，但不重新初始化 Firebase
db = firestore.client()  

line_bot = Blueprint('line_bot', __name__)

# 設定你的 LINE Channel Access Token
LINE_ACCESS_TOKEN = "VdtcUZfBf3jNw78ikkMec2d027aVinjp1Kjj7C/LMi2rwFWoa2KaBN/fYQgQN4lxjkDXlbXRqdhVlJ5TgRlEzWA1fFUS/0g65hVEXQuGZvFPeFrEWZtxoLx6oPj1zgXO2g4gBE2et3eMBU0I1bK50QdB04t89/1O/w1cDnyilFU="
LINE_PUSH_URL = "https://api.line.me/v2/bot/message/push"


# 發送 LINE 訊息的函式
def send_message_to_line(user_id, message):
    # ✅ 直接指定一個已知的測試用 LINE User ID
    test_user_id = "Ub6ae7408691d234a6e8a6cae4d0bac01"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_ACCESS_TOKEN}",
        "X-Line-Retry-Key": str(uuid.uuid4())
    }
    payload = {
        "to": test_user_id,  # ✅ 這裡用測試用的 ID
        "messages": [{"type": "text", "text": message}]
    }

    print(f"🔹 Sending LINE message to: {test_user_id} | Message: {message}")  # 🔍 記錄發送資訊

    response = requests.post(LINE_PUSH_URL, json=payload, headers=headers)
    
    print(f"🔍 LINE API Response: {response.status_code} | {response.text}")  # 🔍 記錄 API 回應


# 手動發送訊息的 API
@line_bot.route('/send_message', methods=['POST'])
def send_message():
    try:
        data = request.json
        user_id = data.get("to")
        messages = data.get("messages", [])
        
        if not user_id or not messages:
            return jsonify({"error": "Missing required fields"}), 400
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {LINE_ACCESS_TOKEN}",
            "X-Line-Retry-Key": str(uuid.uuid4())
        }
        
        payload = {
            "to": "Ub6ae7408691d234a6e8a6cae4d0bac01",
            "messages": [
                {"type": "text", "text": "this is a test message"}
                ]
        }
        
        response = requests.post(LINE_PUSH_URL, json=payload, headers=headers)
        
        if response.status_code == 200:
            return jsonify({"message": "Push message sent successfully"}), 200
        else:
            return jsonify({"error": response.text}), response.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@line_bot.route('/send_upload_failure_message', methods=['POST'])
def send_upload_failure_message():
    try:
        data = request.json
        error_message = data.get("error_message")
        test_user_id = "Ub6ae7408691d234a6e8a6cae4d0bac01"  # 測試專用的 LINE User ID
        
        if not error_message:
            return jsonify({"error": "Missing required fields"}), 400
        
        send_message_to_line(test_user_id, f"File upload failed: {error_message}")
        
        return jsonify({"message": "Upload failure notification sent to test user"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
