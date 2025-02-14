import os
from flask import Blueprint, abort, redirect, request, jsonify
import requests
import uuid

import firebase_admin
from firebase_admin import firestore

from urllib.parse import parse_qsl

from linebot.v3 import (
    WebhookHandler
)
from linebot.v3.exceptions import (
    InvalidSignatureError
)
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    ReplyMessageRequest,
    TextMessage,
    TemplateMessage,
    ImageCarouselTemplate,
    ImageCarouselColumn,
    MessageAction,
    PostbackAction,
    CarouselTemplate,
    CarouselColumn,
    URIAction,
    VideoMessage,
    AudioMessage,
)
from linebot.v3.webhooks import (
    MessageEvent,
    TextMessageContent,
    PostbackEvent,
    PostbackContent,
)

# 🔹 只取得 `db`，但不重新初始化 Firebase
db = firestore.client()

line_blueprint = Blueprint('api/line', __name__)

# 設定你的 LINE Channel Access Token
LINE_MESSAGE_CHANEL_ACCESS_TOKEN = os.environ.get(
    "LINE_MESSAGE_CHANEL_ACCESS_TOKEN")
LINE_MESSAGE_CHANEL_SECRET = os.environ.get("LINE_MESSAGE_CHANEL_SECRET")
LINE_MESSAGE_PUSH_URL = os.environ.get("LINE_MESSAGE_PUSH_URL")
LINE_LOGIN_CHANNEL_ID = os.environ.get("LINE_LOGIN_CHANNEL_ID")
LINE_LOGIN_CHANNEL_SECRET = os.environ.get("LINE_LOGIN_CHANNEL_SECRET")
LINE_LOGIN_REDIRECT_URI = os.environ.get("LINE_LOGIN_REDIRECT_URI")

configuration = Configuration(access_token=LINE_MESSAGE_CHANEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_MESSAGE_CHANEL_SECRET)
with ApiClient(configuration) as api_client:
    line_bot_api = MessagingApi(api_client)

# 發送 LINE 訊息的函式


def send_message_to_line(user_id, meeting_data):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_MESSAGE_CHANEL_ACCESS_TOKEN}",
        "X-Line-Retry-Key": str(uuid.uuid4())
    }
    thumbnailUrl = meeting_data["thumbnailUrl"]
    srcUrl = meeting_data["srcUrl"]
    summary_title = meeting_data["summary"]["title"]
    summary_content = meeting_data["summary"]["content"]
    messages = []
    messages.append(
        {
            "type": "text",
            "text": summary_title
        }
    )
    if srcUrl.endswith('.mp4'):
        messages.append(
            {
                "type": "video",
                "originalContentUrl": srcUrl,
                "previewImageUrl": thumbnailUrl,
                # "trackingId": "track-id"
            }
        )
    else:
        duration = int(
            float(meeting_data["transcription"]["duration"])*1000)
        messages.append(
            {
                "type": "audio",
                "originalContentUrl": srcUrl,
                "duration": duration,
                        # "trackingId": "track-id"
            }
        )
    messages.append({
        "type": "text",
        "text": summary_content,
    })
    payload = {
        "to": user_id,  # ✅ 這裡用測試用的 ID
        "messages": messages
    }

    # 🔍 記錄發送資訊
    print(f"🔹 Sending LINE message to: {user_id} | Message: {messages}")

    response = requests.post(LINE_MESSAGE_PUSH_URL,
                             json=payload, headers=headers)

    # 🔍 記錄 API 回應
    print(f"🔍 LINE API Response: {response.status_code} | {response.text}")


@line_blueprint.route('/login', methods=['GET'])
def login():
    uid = request.headers.get('X-User-Id')
    # LINE Login 授權 URL
    authorization_url = (
        "https://access.line.me/oauth2/v2.1/authorize"
        f"?response_type=code"
        f"&client_id={LINE_LOGIN_CHANNEL_ID}"
        f"&redirect_uri={LINE_LOGIN_REDIRECT_URI}"
        f"&state={uid}"
        f"&scope=profile%20openid%20email"
    )
    return authorization_url


@line_blueprint.route('/login/callback', methods=['GET'])
def login_callback():
    # 接收授權碼和狀態參數
    code = request.args.get('code')
    uid = request.args.get('state')

    # 使用授權碼請求 Access Token
    token_url = "https://api.line.me/oauth2/v2.1/token"
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": LINE_LOGIN_REDIRECT_URI,
        "client_id": LINE_LOGIN_CHANNEL_ID,
        "client_secret": LINE_LOGIN_CHANNEL_SECRET,
    }

    response = requests.post(token_url, headers=headers, data=data)
    token_data = response.json()

    # 檢查是否成功取得 Access Token
    if "access_token" in token_data:
        access_token = token_data["access_token"]

        # 使用 Access Token 獲取用戶資料
        profile_url = "https://api.line.me/v2/profile"
        profile_headers = {"Authorization": f"Bearer {access_token}"}
        profile_response = requests.get(profile_url, headers=profile_headers)
        profile_data = profile_response.json()

        user_doc_ref = db.collection("user").document(uid)
        user_config = user_doc_ref.get().to_dict()
        user_config["preferences"]["lineNotification"] = {
            "enabled": True,
            "uid": profile_data["userId"],
        }
        user_doc_ref.set(user_config, merge=True)

        # 將用戶資料顯示在頁面上
        return redirect(f"/dashboard/profile")
    else:
        return "取得 Access Token 失敗", 400


@line_blueprint.route("/message/callback", methods=['POST'])
def message_callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'


@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    mtext = event.message.text
    print(mtext)
    if mtext == '會議清單':
        send_meeting_list(event)


# PostbackTemplateAction觸發此事件
@handler.add(PostbackEvent)
def handle_postback(event):
    backdata = dict(parse_qsl(event.postback.data))  # 取得Postback資料
    action = backdata.get('action')
    if backdata.get('action') == 'meetingDetail':
        meeting_id = backdata.get('meetingId')
        send_meeting_data(event, meeting_id)


def send_meeting_list(event):
    # 從Firestore獲取對話歷史
    # 查詢 preferences.lineNotification.uid 等於 target_uid 的文件
    collection_ref = db.collection('your_collection_name')  # 替換為你的集合名稱
    query = collection_ref.where('preferences.lineNotification.uid', '==', )

    # 查詢並輸出結果
    results = query.stream()

    for doc in results:
        print(f'Document ID: {doc.id}')
        print(f'Document Data: {doc.to_dict()}')
    meetingsRef = db.collection("user").document(
        "8zAech6MQUenjt6gSnNz8yhTk312").collection("summaries")
    meetings = meetingsRef.get()

    carouselColumns = []

    for meeting in meetings:
        meeting_data = meeting.to_dict()
        if (meeting_data["thumbnailUrl"] != None):
            print(meeting_data["thumbnailUrl"])
            title = meeting_data["summary"]["title"]
            content = meeting_data["summary"]["content"]
            image_url = meeting_data["thumbnailUrl"]
            meeting_id = meeting_data["id"]
            if len(content) > 60:
                content = content[:57] + "..."
            carouselColumns.append(
                CarouselColumn(
                    title=title,
                    text=content,
                    thumbnail_image_url=image_url,
                    # imageBackgroundColor="#4F46E5",
                    # defaultAction=URIAction(
                    #     uri="https://loyal-cat-noble.ngrok-free.app/dashboard/meetingSummary/"+meeting_data["id"]
                    # ),
                    actions=[
                        PostbackAction(
                            label='詳細資訊',
                            data=f'action=meetingDetail&meetingId={meeting_id}'
                        ),
                    ]
                ),
            )
    try:
        message = TemplateMessage(
            alt_text='會議清單',
            template=CarouselTemplate(
                columns=carouselColumns
            )
        )
        # line_bot_api.reply_message(event.reply_token,message)
        line_bot_api.reply_message_with_http_info(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[message]
            )
        )
    except:
        line_bot_api.reply_message(ReplyMessageRequest(
            reply_token=event.reply_token,
            messages=[TextMessage("發生錯誤")]
        ))


def send_meeting_data(event, meeting_id):
    meetingRef = db.collection("user").document(
        "8zAech6MQUenjt6gSnNz8yhTk312").collection("summaries").document(meeting_id)
    meeting = meetingRef.get()
    meeting_data = meeting.to_dict()
    try:
        thumbnailUrl = meeting_data["thumbnailUrl"]
        srcUrl = meeting_data["srcUrl"]
        summary_title = meeting_data["summary"]["title"]
        summary_content = meeting_data["summary"]["content"]
        messages = []
        messages.append(TextMessage(text=summary_title))
        if srcUrl.endswith('.mp4'):
            messages.append(
                VideoMessage(
                    previewImageUrl=thumbnailUrl,
                    originalContentUrl=srcUrl,
                )
            )
        else:
            duration = int(
                float(meeting_data["transcription"]["duration"])*1000)
            messages.append(
                AudioMessage(
                    originalContentUrl=srcUrl,
                    duration=duration,
                )
            )
        messages.append(TextMessage(text=summary_content))
        # line_bot_api.reply_message(event.reply_token,message)
        line_bot_api.reply_message_with_http_info(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=messages
            )
        )
    except:
        line_bot_api.reply_message(ReplyMessageRequest(
            reply_token=event.reply_token,
            messages=[TextMessage("發生錯誤")]
        ))
