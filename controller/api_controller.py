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

from libs.ai import AI
from libs.s3 import S3
from controller.linebot_controller import send_message_to_line

api_blueprint = Blueprint('api', __name__)

RECORDINGS_PATH = os.environ.get("RECORDINGS_PATH", "recordings/")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
CHAT_MODEL = os.environ.get("CHAT_MODEL")
AUDIO_MODEL = os.environ.get("AUDIO_MODEL")

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

from moviepy.video.io.VideoFileClip import VideoFileClip

def extract_first_frame(video_path, output_image_path):
    # 使用 MoviePy 讀取影片
    try:
        with VideoFileClip(video_path) as video:
            # 提取第一幀並保存
            video.save_frame(output_image_path, t=0.0)
            print(f"縮圖已保存到 {output_image_path}")
    except Exception as e:
        print(f"發生錯誤: {e}")

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
            s3_file_name = f"{file_name}-{generate_random_code()}-{formatted_time}.{file_type}"
            key = f"{RECORDINGS_PATH}{s3_file_name}"
            try:
                s3.upload_object(key, file)
            except Exception as e:
                error_message = f"Error uploading file: {str(e)}"
                if uid:
                    send_message_to_line(uid, f"檔案上傳失敗：{error_message}")
                return jsonify({'errorMessage': f'Error uploading file: {str(e)}'}), 500
        else:
            return jsonify({'errorMessage': 'File type not allowed'}), 400
        
    try:
        if(file_type == 'mp4'):
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
                        s3.upload_object(f"{RECORDINGS_PATH}{thumbnail_name}",image_file)
                        
                    video.release()
                
                    # 使用 pydub 加載音頻流
                    audio = AudioSegment.from_file(temp_video_file_path, format=file_type)
                    
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
                            "thumbnailUrl":  f"{request.host_url}api/openvidu/recordings/thumbnails/{thumbnail_name}",
                        }
                    }

                    doc_ref = db.collection("user").document(uid).collection("summaries").document(summary_id)
                    
                    doc_ref.set(response["summary"])

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

                doc_ref = db.collection("user").document(uid).collection("summaries").document(summary_id)
                
                doc_ref.set(response["summary"])

                return jsonify(response)

    except Exception as e:
        error_message = str(e)
        if uid:
            send_message_to_line(uid, f"檔案處理失敗：{error_message}")
        return jsonify({
            "errorMessage": str(e)
        }), 500
        
@api_blueprint.route('/summary/<summary_id>', methods=['DELETE'])
def deleteSummary(summary_id):
    uid = request.headers.get('X-User-Id')
    try:
        doc_ref = db.collection("user").document(uid).collection("summaries").document(summary_id)
            
        doc_ref.delete()
        return jsonify({"message": "success"}), 200
    except Exception as e:
        return jsonify({
            "errorMessage": str(e)
        }), 500