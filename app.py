from flask import Flask, request, jsonify
from flask_cors import CORS
import os
from libs.ai import transcribeAudio, getSummary
import firebase_admin
from firebase_admin import credentials, firestore
import math
import uuid
from datetime import datetime, timezone

# 初始化 Firebase Admin SDK
if not firebase_admin._apps:
    cred = credentials.Certificate("./serviceAccount.json")
    firebase_admin.initialize_app(cred)

# 初始化firestore
db = firestore.client()

app = Flask(__name__)
# CORS(app, resources={r"/*": {"origins": "*"}}) # This is the dangerous part.
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

    print(uid)

    # 儲存音訊檔案到一個臨時路徑
    audio_path = os.path.join('temp_audio', audio_file.filename)
    os.makedirs(os.path.dirname(audio_path), exist_ok=True)
    audio_file.save(audio_path)

    try:
        # 使用 transcribeAudio 庫進行語音轉文字
        transcription = transcribeAudio(audio_path)
        # print(transcription)
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


if __name__ == '__main__':
    app.run(debug=True,use_reloader=False)
