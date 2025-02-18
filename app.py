import argparse
import base64
import cv2
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
from dotenv import load_dotenv
import firebase_admin
from flask import Flask, render_template, request, send_from_directory, redirect
from flask_cors import CORS
import os
from firebase_admin import credentials
import socket

from flask_socketio import SocketIO, emit, send
import numpy as np
import socketio

# try:
#     # 设置命令行参数解析器
#     parser = argparse.ArgumentParser(description="Flask application")
#     parser.add_argument('--env', type=str, default='local', choices=['local', 'dev'],
#                         help="Set the environment to 'local' or 'dev'")
#     parser.add_argument('--port', type=int, default=5000, help="Set the port for the Flask server")
#     args = parser.parse_args()

#     # 根据当前环境来设置加载的 .env 文件
#     if args.env == 'local':
#         load_dotenv('.env.local')
#     else:
#         load_dotenv('.env.dev')
# except Exception as e:
#     # print("Error loading .env file")
#     # 使用預設的 .env 文件
#     load_dotenv('.env.dev')

load_dotenv('.env.local')
# load_dotenv('.env.dev')

# 初始化 Firebase Admin SDK
if not firebase_admin._apps:
    cred = credentials.Certificate("./serviceAccount.json")
    firebase_admin.initialize_app(cred)

from controller.openvidu_controller import openvidu_blueprint
from controller.api_controller import api_blueprint
from controller.line_controller import line_blueprint

app = Flask(__name__,static_folder="templates/assets/", template_folder="templates")
socketio = SocketIO(app, cors_allowed_origins="*")  # 允許跨域請求
CORS(app)

# Register the blueprints with appropriate URL prefixes
app.register_blueprint(api_blueprint, url_prefix='/api')
app.register_blueprint(openvidu_blueprint, url_prefix='/api/openvidu')
app.register_blueprint(line_blueprint, url_prefix='/api/line')  

@app.before_request
def before_request():
    if "/api/" in request.path and not request.path.startswith("/api/"):
        corrected_path = "/api/" + request.path.split("/api/")[1]  # 取出正確的 API 路徑
        return redirect(corrected_path, code=307)  # 307 會保留原 HTTP 方法

# 處理前端路由
@app.route('/<path:path>')
def frontend_routes(path):
    print("path:", path)
    try:
        return send_from_directory(app.static_folder, path)
    except:
        # 如果文件不存在，回傳 index.html，交由前端處理
        return render_template('index.html')

@socketio.on("message")
def handle_message(data):
    def base64_to_cv2(base64_string):
        # 移除 Base64 字首 (data:image/jpeg;base64, ...)
        base64_data = base64_string.split(",")[1] if "," in base64_string else base64_string
        
        # 解碼 Base64
        img_data = base64.b64decode(base64_data)
        
        # 轉換為 numpy 陣列
        np_arr = np.frombuffer(img_data, np.uint8)
        
        # 轉換為 OpenCV 影像
        img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        
        return img
    try:
        # 解析 JSON 資料
        if isinstance(data, str):
            import json
            data = json.loads(data)
        username = data["username"]
        img = base64_to_cv2(data["image"])
        if img is None:
            print("❌ Base64 解碼失敗")
            return 
        
        print(f"影像尺寸: {img.shape}")  # 確保影像正確讀取
        base_options = python.BaseOptions(model_asset_path='gesture_recognizer.task')
        options = vision.GestureRecognizerOptions(base_options=base_options)
        recognizer = vision.GestureRecognizer.create_from_options(options)
        # 初始化 MediaPipe Hands
        mp_hands = mp.solutions.hands
        mp_drawing = mp.solutions.drawing_utils

        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

        with mp_hands.Hands(static_image_mode=True, min_detection_confidence=0.5) as hands:
            results = hands.process(img_rgb)

            if results.multi_hand_landmarks:
                for landmarks in results.multi_hand_landmarks:
                    mp_drawing.draw_landmarks(img, landmarks, mp_hands.HAND_CONNECTIONS)
                    
                # Display the gesture label on the image (if any gesture is recognized)
                # Recognize gestures
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=img_rgb)
                recognition_result = recognizer.recognize(mp_image)

                if recognition_result.gestures:
                    for gesture in recognition_result.gestures:
                        # Get the top gesture and its category name
                        top_gesture = gesture[0]
                        gesture_label = top_gesture.category_name
                        socketio.emit("gestureDetection", {"username":username,"gesture":gesture_label})
       
    except Exception as e:
        print("影像處理錯誤:", e)

# 單一入口路由
@app.route('/')
def index():
    return render_template('index.html')

if __name__ == "__main__":
    SERVER_PORT = os.environ.get("SERVER_PORT", 6080)
    # if args.env == 'local':
    #     app.run(debug=True, port=SERVER_PORT)
    # else:
    #     app.run(debug=False, host="0.0.0.0", port=SERVER_PORT, ssl_context=('cert.pem', 'key.pem'))
    # app.run(debug=True, port=SERVER_PORT, host="0.0.0.0")
    # app.run(debug=False, host="0.0.0.0", port=SERVER_PORT, ssl_context=('server.crt','server.key'))
    socketio.run(app, port=SERVER_PORT, debug=True)
    # socketio.run(app, host="0.0.0.0", port=SERVER_PORT, debug=True, ssl_context=('server.crt','server.key'))

