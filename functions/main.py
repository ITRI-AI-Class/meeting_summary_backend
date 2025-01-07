import os
import math
from flask import Flask, request, jsonify
from flask_cors import CORS
from firebase_functions import https_fn
import firebase_admin
from firebase_admin import credentials, firestore
from libs.ai import transcribeAudio, getSummary
import uuid
from datetime import datetime, timezone

# 初始化 Firebase Admin SDK
if not firebase_admin._apps:
    cred = credentials.Certificate("./serviceAccount.json")
    firebase_admin.initialize_app(cred)

# 初始化firestore
db = firestore.client()

# 初始化 Flask 應用
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

@app.route('/summarize', methods=['POST'])
def process_audio():
    # 檢查是否有上傳音訊檔案
    if 'audio' not in request.files:
        return jsonify({
            "message": "fail",
            "error": "No audio file found"
        }), 400

    audio_file = request.files['audio']
    uid = request.form.get('uid')
    
    # 儲存音訊檔案到一個臨時路徑
    audio_path = os.path.join('/tmp', audio_file.filename)  # Firebase Functions 預設臨時路徑在 /tmp
    os.makedirs(os.path.dirname(audio_path), exist_ok=True)
    audio_file.save(audio_path)

    try:
        # 使用 transcribeAudio 庫進行語音轉文字
        transcription = transcribeAudio(audio_path)
        mapped_segments = list(map(lambda segment: {"id": segment["id"], "startTime": math.floor(
            segment["start"]), "endTime": math.floor(segment["end"]), "text": segment["text"]}, transcription.segments))

        # 使用 getSummary 生成會議摘要
        summary = getSummary(transcription.text)
        summary_id = str(uuid.uuid4())
        date = datetime.now(timezone.utc).isoformat()
        # 構建返回的 JSON 格式
        response = {
            "message": "success",
            "data": {
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
        
        doc_ref.set(response["data"])

        return jsonify(response)

    except Exception as e:
        return jsonify({
            "message": "fail",
            "error": str(e)
        }), 500

# Firebase Function 入口
@https_fn.on_request(max_instances=1)
def meetingAI(req: https_fn.Request) -> https_fn.Response:
    with app.request_context(req.environ):
        return app.full_dispatch_request()
