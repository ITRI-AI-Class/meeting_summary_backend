from datetime import datetime, timezone
from io import BytesIO
import math
import os
import firebase_admin
from pydub import AudioSegment
import random
import string
from tempfile import NamedTemporaryFile
import uuid
from firebase_admin import firestore, credentials
from flask import Blueprint, jsonify, request

from libs.ai import AI
from libs.s3 import S3

api_blueprint = Blueprint('api', __name__)

RECORDINGS_PATH = os.environ.get("RECORDINGS_PATH", "recordings/")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
CHAT_MODEL = os.environ.get("CHAT_MODEL")
AUDIO_MODEL = os.environ.get("AUDIO_MODEL")

# 初始化 Firebase Admin SDK
if not firebase_admin._apps:
    cred = credentials.Certificate("./serviceAccount.json")
    firebase_admin.initialize_app(cred)

# 初始化firestore
db = firestore.client()

s3 = S3()

allowed_file_types = {'mp3', 'mp4', 'm4a', 'wav', 'webm'}  # 許可的檔案擴展名

# 檢查檔案擴展名是否有效
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_file_types

def generate_random_code(length=12):
    characters = string.ascii_letters + string.digits  # 包含大小寫字母和數字
    return ''.join(random.choices(characters, k=length))

@api_blueprint.route('/summarize', methods=['POST'])
def summarize():
    ai = AI(api_key=GROQ_API_KEY, chat_model=CHAT_MODEL, audio_model=AUDIO_MODEL, temperature=0)
    # 檢查是否有上傳音訊檔案
    if 'file' not in request.files and 's3_file_name' not in request.form:
        return jsonify({
            "errorMessage": "No file found",
        }), 400

    uid = request.form.get('uid')
    key = ''
    file_name = ''
    file_type = ''

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
            key = f"{RECORDINGS_PATH}{file_name}-{generate_random_code()}-{formatted_time}.{file_type}"
            try:
                s3.upload_object(key, file)
            except Exception as e:
                return jsonify({'errorMessage': f'Error uploading file: {str(e)}'}), 500
        else:
            return jsonify({'errorMessage': 'File type not allowed'}), 400
        
    try:
        # 使用 transcribeAudio 庫進行語音轉文字
        # 假設 video_stream 已經從 S3 加載成功
        video_stream = BytesIO()
        s3.download_object(key, video_stream)
        # if result is None:
        #     return jsonify({'errorMessage': 'Error downloading file from S3'}), 500
        video_stream.seek(0)

        # 使用 pydub 加載音頻流
        audio = AudioSegment.from_file(video_stream, format=file_type)

        # 將音頻保存為臨時文件
        with NamedTemporaryFile(suffix=".mp3") as temp_file:
            audio.export(temp_file.name, format="mp3")
            temp_file_path = temp_file.name  # 獲取臨時文件路徑
            print(temp_file_path)
            with open(temp_file_path, "rb") as file:
                transcription = ai.transcribe_audio(file)
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
                "thumbnailUrl": "https://images.unsplash.com/photo-1542744173-8e7e53415bb0?auto=format&fit=crop&q=80" # 可改為動態的 
            }
        }

        doc_ref = db.collection("user").document(uid).collection("summaries").document(summary_id)
        
        doc_ref.set(response["summary"])

        return jsonify(response)

    except Exception as e:
        return jsonify({
            "errorMessage": str(e)
        }), 500