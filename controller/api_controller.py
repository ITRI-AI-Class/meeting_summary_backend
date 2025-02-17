from datetime import datetime, timezone
from io import BytesIO
import math
import os
import cv2
import firebase_admin
import numpy as np
from pydub import AudioSegment
import random
import string
from tempfile import NamedTemporaryFile
import uuid
from firebase_admin import firestore, credentials
from flask import Blueprint, jsonify, request

from controller.line_controller import send_message_to_line
from libs.ai import AI
from libs.s3 import S3

api_blueprint = Blueprint('api', __name__)

# 網站功能上下文
WEBSITE_CONTEXT = """
你是一個專門協助用戶使用我們網站的客服機器人。你的名字是 Forgetful Buddy。
請遵循以下規則：

1. 始終使用繁體中文回答
2. 保持友善且專業的態度
3. 只回答與網站功能相關的問題
4. 如果問題與網站功能無關，禮貌地引導用戶回到網站相關的主題
5. 對於不確定的問題，建議用戶留下email，以便技術支援聯繫

網站主要功能包括：
1.幫使用者記錄會議錄音
2.上傳會議錄音並生成文字記錄
3.提供會議重點摘要

如有技術問題，請建議用戶：
1. 重新整理頁面
2. 確認網路連線
3. 如果問題持續，聯繫技術支援

如果有跟以上問題不相干的，絕對不可以回答!!!
並且禮貌地引導用戶回到網站相關的主題。
"""
# 歡迎語
WELCOME_CONTEXT = """
您好！我是 Forgetful Buddy，專門協助您使用我們網站的智能客服機器人，很高興為您服務！😊

我們的網站可以幫助您：

記錄並保存會議錄音。
上傳錄音檔案並快速生成文字記錄。
提供會議重點摘要，讓您輕鬆掌握內容！
如果您在使用網站的過程中有任何問題，都可以隨時問我喔！如果遇到技術問題，也可以依循以下步驟嘗試解決：

重新整理頁面
確認網路連線
或留下您的 email，我們的技術支援團隊會儘快與您聯繫。
讓我們一起高效管理會議吧！請問我可以幫您什麼呢？ 😊
"""

RECORDINGS_PATH = os.environ.get("RECORDINGS_PATH", "recordings/")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
CHAT_MODEL = os.environ.get("CHAT_MODEL")
AUDIO_MODEL = os.environ.get("AUDIO_MODEL")

# 初始化firestore
db = firestore.client()

s3 = S3()

allowed_file_types = {'mp3', 'mp4', 'm4a', 'wav', 'webm'}  # 許可的檔案擴展名

ai = AI(api_key=GROQ_API_KEY, chat_model=CHAT_MODEL,
        audio_model=AUDIO_MODEL, temperature=0)

# 檢查檔案擴展名是否有效


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_file_types


def generate_random_code(length=12):
    characters = string.ascii_letters + string.digits  # 包含大小寫字母和數字
    return ''.join(random.choices(characters, k=length))


@api_blueprint.route('/summarize', methods=['POST'])
def summarize():
    # 檢查是否有上傳音訊檔案
    if 'file' not in request.files and 's3_file_name' not in request.form:
        return jsonify({
            "errorMessage": "No file found",
        }), 400

    uid = request.form.get('uid')
    key = ''
    file_name = ''
    file_type = ''
    summary_id = request.form.get('summary_id', str(uuid.uuid4()))
    s3_file_name = request.form.get('s3_file_name')
    if s3_file_name and allowed_file(s3_file_name):
        file_name = s3_file_name.split('.')[0]
        file_type = s3_file_name.split('.')[1]
        key = RECORDINGS_PATH + s3_file_name
    else:
        file = request.files['file']
        if file and allowed_file(file.filename):
            file_name = file.filename.split('.')[0]
            file_type = file.filename.split('.')[1]
            if file_name == '':
                return jsonify({'errorMessage': 'No selected file'}), 400
            # 獲取當前時間
            now = datetime.now()
            # 格式化為指定格式
            formatted_time = now.strftime("%Y-%m-%dT%H%M%S")
            s3_file_name = f"{file_name}-{generate_random_code()}-{formatted_time}.{file_type}"
            key = f"{RECORDINGS_PATH}{s3_file_name}"
            try:
                s3.upload_object(key, file)
            except Exception as e:
                error_message = f"Error uploading file: {str(e)}"
                return jsonify({'errorMessage': f'Error uploading file: {str(e)}'}), 500
        else:
            error_message = str(e)
            return jsonify({'errorMessage': 'File type not allowed'}), 400

    try:
        user_profile_ref = db.collection("user").document(uid)
        user_profile = user_profile_ref.get().to_dict()
        line_id = user_profile["preferences"]["lineNotification"]["uid"]
        line_notification_enabled = user_profile["preferences"]["lineNotification"]["enabled"]
        if (file_type == 'mp4'):
            with NamedTemporaryFile(suffix=".mp4") as temp_video_file:
                s3.download_object(key, temp_video_file)
                temp_video_file_path = temp_video_file.name  # 獲取臨時文件路徑

                # 提取影片第一幀
                video = cv2.VideoCapture(temp_video_file_path)

                # 設置到指定的幀數
                video.set(cv2.CAP_PROP_POS_FRAMES, 24)

                success, frame = video.read()

                if success:
                    thumbnail_name = f"{key.split('/')[-1].split('.')[0]}_thumbnail.jpg"
                    temp_thumbnail_file_path = f"/tmp/{key.split('/')[-1].split('.')[0]}_thumbnail.jpg"
                    cv2.imwrite(temp_thumbnail_file_path, frame)
                    with open(temp_thumbnail_file_path, "rb") as image_file:
                        s3.upload_object(
                            f"{RECORDINGS_PATH}{thumbnail_name}", image_file)

                    video.release()

                    # 使用 pydub 加載音頻流
                    audio = AudioSegment.from_file(
                        temp_video_file_path, format=file_type)

                    # 將音頻保存為臨時文件
                    with NamedTemporaryFile(suffix=".mp3") as temp_audio_file:
                        audio.export(temp_audio_file.name, format="mp3")
                        temp_audio_file_path = temp_audio_file.name  # 獲取臨時文件路徑
                        print(temp_audio_file_path)
                        with open(temp_audio_file_path, "rb") as audio_file:
                            transcription = ai.transcribe_audio(audio_file)

                    # print(transcription)
                    mapped_segments = list(map(
                        lambda segment:
                            {
                                "id": segment["id"],
                                "startTime": math.floor(segment["start"]),
                                "endTime": math.floor(segment["end"]),
                                "text": segment["text"]
                            },
                        transcription.segments))

                    # 使用 getSummary 生成會議摘要
                    summary = ai.get_summary(transcription.text)
                    date = datetime.now(timezone.utc).isoformat()
                    # 構建返回的 JSON 格式
                    response = {
                        "summary": {
                            "id": summary_id,
                            "date": date,
                            "summary": summary,
                            "transcription": {
                                "duration": transcription.duration,
                                "segments": mapped_segments  # 傳遞時間段的轉錄內容
                            },
                            "srcUrl": f"{request.host_url}api/openvidu/recordings/{s3_file_name}",
                            "thumbnailUrl":  f"{request.host_url}api/openvidu/recordings/thumbnails/{thumbnail_name}",
                        }
                    }

                    doc_ref = db.collection("user").document(
                        uid).collection("summaries").document(summary_id)

                    doc_ref.set(response["summary"])

                    if line_id and line_notification_enabled:
                        send_message_to_line(line_id, response["summary"])
                    return jsonify(response)
                else:
                    video.release()
                    return jsonify({"error": "Failed to extract frame from video"}), 500
        else:
            with NamedTemporaryFile(suffix=".mp3") as temp_audio_file:
                s3.download_object(key, temp_audio_file)
                with open(temp_audio_file.name, "rb") as audio_file:
                    transcription = ai.transcribe_audio(audio_file)
                # print(transcription)
                mapped_segments = list(map(
                    lambda segment:
                        {
                            "id": segment["id"],
                            "startTime": math.floor(segment["start"]),
                            "endTime": math.floor(segment["end"]),
                            "text": segment["text"]
                        },
                    transcription.segments))

                # 使用 getSummary 生成會議摘要
                summary = ai.get_summary(transcription.text)
                summary_id = str(uuid.uuid4())
                date = datetime.now(timezone.utc).isoformat()
                # 構建返回的 JSON 格式
                response = {
                    "summary": {
                        "id": summary_id,
                        "date": date,
                        "summary": summary,
                        "transcription": {
                            "duration": transcription.duration,
                            "segments": mapped_segments  # 傳遞時間段的轉錄內容
                        },
                        "srcUrl": f"{request.host_url}api/openvidu/recordings/{s3_file_name}",
                        "thumbnailUrl":  None,
                    }
                }

                doc_ref = db.collection("user").document(
                    uid).collection("summaries").document(summary_id)

                doc_ref.set(response["summary"])

                if line_id and line_notification_enabled:
                    send_message_to_line(line_id, response["summary"])
                return jsonify(response)

    except Exception as e:
        return jsonify({
            "errorMessage": str(e)
        }), 500


@api_blueprint.route('/summary/<summary_id>', methods=['DELETE'])
def delete_summary(summary_id):
    uid = request.headers.get('X-User-Id')
    try:
        doc_ref = db.collection("user").document(
            uid).collection("summaries").document(summary_id)

        doc_ref.delete()
        return jsonify({"message": "success"}), 200
    except Exception as e:
        return jsonify({
            "errorMessage": str(e)
        }), 500


@api_blueprint.route('/chatbot/history', methods=['GET'])
def get_chatbot_history():
    uid = request.headers.get('X-User-Id')
    try:
        # 從Firestore獲取對話歷史
        chat_ref = db.collection("user").document(
            uid).collection("chatbot").document("history")
        chat_doc = chat_ref.get()

        # 準備對話歷史
        if chat_doc.exists:
            chat_history = chat_doc.to_dict()
        else:
            chat_history = {
                "messages": [
                    {
                        "role": "assistant",
                        "content": WELCOME_CONTEXT,
                        "date": datetime.now(timezone.utc).isoformat()
                    }
                ],
                "lastUpdated": datetime.now(timezone.utc).isoformat()
            }

        # 更新Firestore中的對話記錄
        chat_ref.set(chat_history, merge=True)

        return jsonify(chat_history)

    except Exception as e:
        return jsonify({
            "errorMessage": str(e)
        }), 500


@api_blueprint.route('/chatbot/message', methods=['POST'])
def get_chatbot_message():
    try:
        # 獲取請求數據
        data = request.json
        uid = data.get('uid')
        message = data.get('message')

        if not message:
            return jsonify({
                "errorMessage": "Message is required"
            }), 400

        # 從Firestore獲取對話歷史
        chat_ref = db.collection("user").document(
            uid).collection("chatbot").document("history")
        chat_doc = chat_ref.get()

        # 準備對話歷史
        if chat_doc.exists:
            chat_history_messages = chat_doc.to_dict().get('messages', [])
        else:
            chat_history_messages = [
                {
                    "role": "assistant",
                    "content": WELCOME_CONTEXT,
                    "date": datetime.now(timezone.utc).isoformat()
                }
            ]

        # 添加用戶新消息到歷史記錄
        current_message = {
            "role": "user",
            "content": message,
            "date": datetime.now(timezone.utc).isoformat()
        }
        chat_history_messages.append(current_message)

        # 準備發送給ChatGroq的消息
        messages = [{"role": chat["role"], "content": chat["content"]}
                    for chat in chat_history_messages]

        messages = [{
            "role": "system",
            "content": WEBSITE_CONTEXT,
        }] + messages

        # 調用ChatGroq API
        bot_response = ai.get_chatbot_message(str(messages))

        # 將機器人的回應添加到歷史記錄
        bot_message = {
            "role": "assistant",
            "content": bot_response,
            "date": datetime.now(timezone.utc).isoformat()
        }
        chat_history_messages.append(bot_message)

        # 更新Firestore中的對話記錄
        chat_data = {
            "messages": [chat for chat in chat_history_messages if chat["role"] != "system"],
            "lastUpdated": datetime.now(timezone.utc).isoformat()
        }
        chat_ref.set(chat_data, merge=True)

        return jsonify(chat_data)

    except Exception as e:
        return jsonify({
            "errorMessage": str(e)
        }), 500
