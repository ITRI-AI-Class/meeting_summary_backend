import os
from flask import Blueprint, abort, redirect, request, jsonify
import requests
import uuid
import json
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
    ButtonsTemplate, 
    TemplateMessage,
    FlexMessage
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
NGROK_URL = "https://mainly-deep-sole.ngrok-free.app"  # 更新為 ngrok 產生的 HTTPS URL

def send_message_to_line(user_id, meeting_data):
    try:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {LINE_MESSAGE_CHANEL_ACCESS_TOKEN}",
            "X-Line-Retry-Key": str(uuid.uuid4())
        }
        thumbnailUrl = meeting_data["thumbnailUrl"]
        srcUrl = meeting_data["srcUrl"]
        summary_title = meeting_data["summary"]["title"]
        summary_content = meeting_data["summary"]["content"]

        # ✅ 替換 srcUrl 的本機網址，改用 ngrok 的公開 HTTPS 網址
        if srcUrl.startswith("http://127.0.0.1:6080"):
            srcUrl = srcUrl.replace("http://127.0.0.1:6080", NGROK_URL)
            print(f"✅ Updated srcUrl: {srcUrl}")  # 確保 URL 是 HTTPS

        # if thumbnailUrl:  # 只有在 `thumbnailUrl` 存在時才替換
        #     if thumbnailUrl.startswith("http://127.0.0.1:6080"):
        #         thumbnailUrl = thumbnailUrl.replace("http://127.0.0.1:6080", NGROK_URL)
        #         print(f"✅ Updated thumbnailUrl: {thumbnailUrl}")
        # ✅ 如果 `thumbnailUrl` 無效（None、空值、127.0.0.1、localhost），改用預設圖片
        if not thumbnailUrl or "127.0.0.1" in thumbnailUrl or "localhost" in thumbnailUrl:
            print("⚠️ 縮圖 URL 無效，使用預設縮圖")
            thumbnailUrl = "https://i.imgur.com/iMHSEfN.png"  # **使用你提供的預設縮圖**
        # 🔹 **MP4 & MP3 產生 Flex Message，並讓整個訊息可點擊**
        flex_content = {
            "type": "bubble",
            # "hero": {
            #     "type": "image",
            #     "url": thumbnailUrl,
            #     "size": "full",
            #     "aspectRatio": "16:9",
            #     "aspectMode": "cover",
            # },
            "hero": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "image",
                        "url": thumbnailUrl,  # ✅ 你的縮圖
                        "size": "full",
                        "aspectRatio": "16:9",
                        "aspectMode": "cover"
                    },
                    {
                        "type": "box",
                        "layout": "vertical",
                        "contents": [
                            {
                                "type": "image",
                                "url": "https://i.imgur.com/WaNVO4d.png",  # ✅ 你的「播放 Icon」
                                "size": "40px",  # 控制 Icon 大小
                                "aspectMode": "fit"
                            }
                        ],
                        "position": "absolute",
                        "offsetBottom": "40%",
                        "offsetStart": "40%",
                        "offsetEnd": "40%"
                    }
                ]
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "text",
                        "text": summary_title,
                        "weight": "bold",
                        "size": "xl",
                        "wrap": True
                    },
                    {
                        "type": "text",
                        "text": summary_content,
                        "size": "sm",
                        "wrap": True,
                        "margin": "md"
                    }
                ]
            },
            # ✅ 讓整個訊息可點擊
            "action": {
                "type": "uri",
                "uri": srcUrl
            }
        }

        # ✅ 修正 FlexMessage 物件創建方式
        flex_message = {
            "type": "flex",
            "altText": "📺 點擊觀看會議影片" if srcUrl.endswith('.mp4') else "🎵 點擊播放會議音檔",
            "contents": flex_content
        }

        payload = {
                "to": user_id,
                "messages": [flex_message]  # **直接傳 JSON，不需要 `model_dump_json()`**
        }

        # 🔍 記錄發送資訊
        print(f"🔹 Sending LINE message to: {user_id} | Message: {json.dumps(payload, indent=2)}")

        response = requests.post(LINE_MESSAGE_PUSH_URL, json=payload, headers=headers)

        # 🔍 記錄 API 回應
        print(f"🔍 LINE API Response: {response.status_code} | {response.text}")
        print(f"🔍 Checking srcUrl: {srcUrl}")
        print(f"🔍 Checking thumbnailUrl: {thumbnailUrl}")
    
    except Exception as e:
        print(f"❌ 發送 LINE 訊息時發生錯誤: {str(e)}")
    

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
    print("📩 LINE Webhook 觸發了!")
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    print(f"📩 收到 Webhook 事件: {body}")  # 確認 LINE 有送 Webhook
    if not signature:
        print("❌ 沒有 X-Line-Signature，可能不是 LINE 發送的")
        abort(400)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        print("❌ Webhook 驗證失敗")
        abort(400)
    return 'OK'


@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    mtext = event.message.text
    print(f"🔹 收到使用者訊息: {mtext}")  # 確認有收到訊息
    if mtext == "會議清單":
        print("✅ 執行 send_meeting_list 函式")  # 確認 `send_meeting_list` 有執行
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
    # query = collection_ref.where('preferences.lineNotification.uid', '==', )

    # # 查詢並輸出結果
    # results = query.stream()

    # for doc in results:
    #     print(f'Document ID: {doc.id}')
    #     print(f'Document Data: {doc.to_dict()}')
    
    
    meetingsRef = db.collection("user").document(
        "QazuaKKg08gGXP37XDvUtsF0pbv1").collection("summaries")
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
        "QazuaKKg08gGXP37XDvUtsF0pbv1").collection("summaries").document(meeting_id)
    meeting = meetingRef.get()
    meeting_data = meeting.to_dict()
    try:
        thumbnailUrl = meeting_data["thumbnailUrl"]
        srcUrl = meeting_data["srcUrl"]
        summary_title = meeting_data["summary"]["title"]
        summary_content = meeting_data["summary"]["content"]

        # ✅ 替換 srcUrl 的本機網址，改用 ngrok 的公開 HTTPS 網址
        if srcUrl.startswith("http://127.0.0.1:6080"):
            srcUrl = srcUrl.replace("http://127.0.0.1:6080", NGROK_URL)
            print(f"✅ Updated srcUrl: {srcUrl}")  # 確保 URL 是 HTTPS
        if not thumbnailUrl or "127.0.0.1" in thumbnailUrl or "localhost" in thumbnailUrl:
            print("⚠️ 縮圖 URL 無效，使用預設縮圖")
            thumbnailUrl = "https://i.imgur.com/iMHSEfN.png"  # **使用你提供的預設縮圖**
        
        # ✅ 確保 `altText` 不是空的
        alt_text = "📺 點擊觀看會議影片" if srcUrl.endswith('.mp4') else "🎵 點擊播放會議音檔"
        # ✅ 產生與摘要通知相同的 `Flex Message`
        flex_content = {
            "type": "bubble",
            "hero": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "image",
                        "url": thumbnailUrl,  # ✅ 你的縮圖
                        "size": "full",
                        "aspectRatio": "16:9",
                        "aspectMode": "cover"
                    },
                    {
                        "type": "box",
                        "layout": "vertical",
                        "contents": [
                            {
                                "type": "image",
                                "url": "https://i.imgur.com/WaNVO4d.png",  # ✅ 你的「播放 Icon」
                                "size": "40px",  # 控制 Icon 大小
                                "aspectMode": "fit"
                            }
                        ],
                        "position": "absolute",
                        "offsetBottom": "40%",
                        "offsetStart": "40%",
                        "offsetEnd": "40%"
                    }
                ]
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "text",
                        "text": summary_title,
                        "weight": "bold",
                        "size": "xl",
                        "wrap": True
                    },
                    {
                        "type": "text",
                        "text": summary_content,
                        "size": "sm",
                        "wrap": True,
                        "margin": "md"
                    }
                ]
            },
            # ✅ 讓整個訊息可點擊
            "action": {
                "type": "uri",
                "uri": srcUrl
            }
        }

        flex_message = {
            "type": "flex",
            "altText": alt_text,  # 🔥 確保 `altText` 存在
            "contents": flex_content
        }
        # ✅ 發送 `Flex Message`
        response = requests.post(
            LINE_MESSAGE_PUSH_URL,
            json={
                "to": event.source.user_id,
                "messages": [flex_message]
            },
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {LINE_MESSAGE_CHANEL_ACCESS_TOKEN}"
            }
        )

        print(f"✅ 發送 `send_meeting_data` 成功: {response.status_code} | {response.text}")
        
    except:
        line_bot_api.reply_message(ReplyMessageRequest(
            reply_token=event.reply_token,
            messages=[TextMessage("發生錯誤")]
        ))
