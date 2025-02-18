import os
import re
from flask import Blueprint, Response, jsonify, request
from livekit.api import AccessToken, VideoGrants, TokenVerifier, WebhookReceiver, EncodedFileOutput, EncodedFileType
from livekit import api
from livekit.api import egress_service
from livekit.protocol import egress as proto_egress
from libs.s3 import S3
from botocore.response import StreamingBody
from botocore.exceptions import ClientError

LIVEKIT_API_KEY = os.environ.get("LIVEKIT_API_KEY", "devkey")
LIVEKIT_API_SECRET = os.environ.get("LIVEKIT_API_SECRET", "secret")
LIVEKIT_URL = os.environ.get("LIVEKIT_URL", "http://localhost:7880")
RECORDINGS_PATH = os.environ.get("RECORDINGS_PATH", "recordings/")
RECORDING_FILE_PORTION_SIZE = 5 * 1024 * 1024  # 5MB

s3 = S3()

openvidu_blueprint = Blueprint('api/openvidu', __name__)

@openvidu_blueprint.route("/token", methods=['POST'])
def create_token():
    room_name = request.json.get("roomName")
    participant_name = request.json.get("participantName")

    if not room_name or not participant_name:
        return {"errorMessage": "roomName and participantName are required"}, 400

    token = (
        AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
        .with_identity(participant_name)
        .with_grants(VideoGrants(room_join=True, room=room_name))
    )
    return {"serverUrl": LIVEKIT_URL,"token": token.to_jwt()}


token_verifier = TokenVerifier(LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
webhook_receiver = WebhookReceiver(token_verifier)

@openvidu_blueprint.route("/livekit/webhook", methods=["POST"])
def receive_webhook():
    auth_token = request.headers.get("Authorization")

    if not auth_token:
        return "Authorization header is required", 401

    try:
        event = webhook_receiver.receive(request.data.decode("utf-8"), auth_token)
        print("LiveKit Webhook:", event)
        return "ok"
    except:
        print("Authorization header is not valid")
        return "Authorization header is not valid", 401

@openvidu_blueprint.route("/recordings/start", methods=["POST"])
async def start_recording():
    lkapi = api.LiveKitAPI(url=LIVEKIT_URL, api_key=LIVEKIT_API_KEY, api_secret=LIVEKIT_API_SECRET)
    egress = lkapi.egress
    
    room_name = request.json.get("roomName")

    if not room_name:
        return jsonify({"errorMessage": "roomName is required"}), 400

    active_recording = await get_active_recording_by_room(egress=egress, room_name=room_name)

    if active_recording:
        return jsonify({"errorMessage": "Recording already started for this room"}), 409

    try:
        
        file_output = proto_egress.EncodedFileOutput(
            file_type=EncodedFileType.MP4,
            filepath=f"{RECORDINGS_PATH}{room_name}-{{room_id}}-{{time}}",
        )

        egress_request =  proto_egress.RoomCompositeEgressRequest(
            room_name=room_name,
            file=file_output,
        )

        egress_info = await egress.start_room_composite_egress(start=egress_request)
        
        file = egress_info.file_results[0]
        
        recording = {
            "name": file.filename.split("/").pop(),
            "startedAt": egress_info.started_at / 1_000_000
        }

        return '', 200
    except Exception as e:
        print("Error starting recording.", e)
        return jsonify({"errorMessage": "Error starting recording"}), 500

@openvidu_blueprint.route("/recordings/stop", methods=["POST"])
async def stop_recording():
    lkapi = api.LiveKitAPI(url=LIVEKIT_URL, api_key=LIVEKIT_API_KEY, api_secret=LIVEKIT_API_SECRET)
    egress = lkapi.egress
    
    room_name = request.json.get("roomName")

    if not room_name:
        return jsonify({"errorMessage": "roomName is required"}), 400

    active_recording = await get_active_recording_by_room(egress=egress, room_name=room_name)

    if not active_recording:
        return jsonify({"errorMessage": "Recording not started for this room"}), 409

    try:
        
        egress_request =  proto_egress.StopEgressRequest(
            egress_id=active_recording
        )
        
        egress_info = await egress.stop_egress(stop=egress_request)

        print(egress_info)

        file = egress_info.file_results[0]

        recording = {
            "id": egress_info.egress_id,
            "name": file.filename.split("/").pop(),
            # "startedAt": egress_info.started_at / 1_000_000,
            # "size": file.size
        }

        return jsonify({"recording": recording})
    except Exception as e:
        print("Error stopping recording.", e)
        return jsonify({"errorMessage": "Error stopping recording"}), 500

@openvidu_blueprint.route("/recordings", methods=["GET"])
def list_recordings():
    recording_id = request.args.get("recordingId")
    room_name = request.args.get("roomName")
    room_id = request.args.get("roomId")

    try:
        key_start = f"{RECORDINGS_PATH}{room_name}-{room_id if room_id else ''}" if room_name else RECORDINGS_PATH
        key_end = ".mp4.json"
        regex = re.compile(f"^{key_start}.*{key_end}$")

        payload_keys = s3.list_objects(RECORDINGS_PATH, regex)

        recordings = [get_recording_info(payload_key) for payload_key in payload_keys]
        sorted_recordings = filter_and_sort_recordings(recordings, room_name, room_id, recording_id)

        return jsonify({"recordings": sorted_recordings})
    except Exception as e:
        print("Error listing recordings.", e)
        return jsonify({"errorMessage": "Error listing recordings"}), 500

async def get_active_recording_by_room(egress : egress_service.EgressService, room_name):
    try:
        request = proto_egress.ListEgressRequest(
            room_name=room_name,
            active=True
        )
        
        egresses = await egress.list_egress(list=request)
        return egresses.items[0].egress_id if egresses else None
    except Exception as e:
        print("Error listing egresses.", e)
        return None

def get_recording_info(payload_key):
    try:
        data = s3.get_object_as_json(payload_key)
        recording_key = payload_key.replace(".json", "")
        size = s3.get_object_size(recording_key)

        recording_name = recording_key.split("/").pop()

        return {
            "id": data["egress_id"],
            "name": recording_name,
            "roomName": data["room_name"],
            "roomId": data["room_id"],
            "startedAt": data["started_at"] / 1_000_000,
            "size": size
        }
    except Exception as e:
        print("Error retrieving recording info.", e)
        return None

def filter_and_sort_recordings(recordings, room_name, room_id, recording_id):
    filtered_recordings = recordings

    if room_name or room_id or recording_id:
        filtered_recordings = [
            recording for recording in recordings
            if (not room_name or recording["roomName"] == room_name) and
               (not room_id or recording["roomId"] == room_id) and
               (not recording_id or recording["id"] == recording_id)
        ]

    return sorted(filtered_recordings, key=lambda x: x["startedAt"], reverse=True)

@openvidu_blueprint.route("/recordings/<recording_name>", methods=["GET"])
def get_recording(recording_name):
    range_header = request.headers.get("Range")
    key = RECORDINGS_PATH + recording_name

    try:
        if not s3.exists(key):
            return jsonify({"errorMessage": "Recording not found"}), 404

        size = s3.get_object_size(key)

        if range_header:
            parts = range_header.replace("bytes=", "").split("-")
            start = int(parts[0]) if parts[0] else 0
            end = int(parts[1]) if len(parts) > 1 and parts[1] else start + RECORDING_FILE_PORTION_SIZE
        else:
            start, end = 0, min(RECORDING_FILE_PORTION_SIZE, size - 1)

        end = min(end, size - 1)

        stream: StreamingBody = s3.get_object(key, range_start=start, range_end=end)

        headers = {
            "Content-Type": "video/mp4",
            "Content-Range": f"bytes {start}-{end}/{size}",
            "Content-Length": str(end - start + 1),
            "Accept-Ranges": "bytes",
            "Cache-Control": "no-cache",
        }

        return Response(stream.read(), status=206, headers=headers)

    except ClientError as e:
        return jsonify({"errorMessage": "Error retrieving recording", "details": str(e)}), 500
    except Exception as e:
        print("Error retrieving recording.", e)
        return jsonify({"errorMessage": "Unexpected error occurred"}), 500

@openvidu_blueprint.route("/recordings/thumbnails/<thumbnail_name>", methods=["GET"])
def get_recording_thumbnail(thumbnail_name):
    key = RECORDINGS_PATH + thumbnail_name

    try:
        if not s3.exists(key):
            return jsonify({"errorMessage": "Recording not found"}), 404

        image_stream = s3.get_object(key)
        
        # 獲取圖片的 MIME 類型 (預設為 image/jpeg)
        headers = {
            "Content-Type": 'image/jpeg',
        }
        # 回傳檔案流作為 HTTP 回應
        return Response(image_stream.read(), headers=headers)

    except ClientError as e:
        return jsonify({"errorMessage": "Error retrieving recording", "details": str(e)}), 500
    except Exception as e:
        print("Error retrieving recording.", e)
        return jsonify({"errorMessage": "Unexpected error occurred"}), 500

@openvidu_blueprint.route("/recordings/stream/<recording_name>", methods=["GET"])
def get_recording_stream(recording_name):
    range_header = request.headers.get("Range")
    key = RECORDINGS_PATH + recording_name

    try:
        size = s3.get_object_size(key)

        if range_header:
            parts = range_header.replace("bytes=", "").split("-")
            start = int(parts[0]) if parts[0] else 0
            end = int(parts[1]) if len(parts) > 1 and parts[1] else start + RECORDING_FILE_PORTION_SIZE
        else:
            start, end = 0, min(RECORDING_FILE_PORTION_SIZE, size - 1)

        end = min(end, size - 1)
        range_params = {"start": start, "end": end}

        stream = s3.get_object(key, range_params)
        return jsonify({"stream": stream.read().decode(), "size": size, "start": start, "end": end})

    except ClientError as e:
        return jsonify({"errorMessage": "Error retrieving recording", "details": str(e)}), 500
    except Exception as e:
        print("Error retrieving recording.", e)
        return jsonify({"errorMessage": "Unexpected error occurred"}), 500


@openvidu_blueprint.route("/recordings/<recording_name>", methods=["DELETE"])
def delete_recording(recording_name):
    key = RECORDINGS_PATH + recording_name
    exists = s3.exists(key)

    if not exists:
        return jsonify({"errorMessage": "Recording not found"}), 404

    try:
        # Delete the recording file and metadata file from S3
        s3.delete_object(key)
        s3.delete_object(f"{key}.json")
        return jsonify({"message": "Recording deleted"})
    except Exception as error:
        print("Error deleting recording.", error)
        return jsonify({"errorMessage": "Error deleting recording"}), 500
