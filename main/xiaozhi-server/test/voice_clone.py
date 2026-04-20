"""
豆包TTS 2.0 语音克隆工具
直接修改下面的配置，然后运行即可
"""
import uuid
import json
import base64
import asyncio
import wave
import time
import requests
import websockets

# =============================================
#  在这里控制要执行的操作（改成 True/False）
# =============================================
DO_TRAIN = False       # 已在控制台训练好，不需要
DO_QUERY = False       # 已在控制台训练好，不需要
DO_TEST  = True        # 直接测试合成

# =============================================
#  在这里配置参数
# =============================================
AUDIO_FILE = r"F:\job-in-cn\xiaozhi-esp32-server\main\xiaozhi-server\test_fun_asr_nano\audio\chafang.wav"
SPEAKER_ID = "S_7WsbK8YQ1"              # 控制台训练好的 speaker_id
LANGUAGE   = 0                          # 0=中文, 1=英文
TEST_TEXT  = "你好，我是你的语音克隆分身，听听像不像你？今天天气真不错，我们一起出去耍嘛。"

# =============================================
#  API 配置（新版控制台）
# =============================================
API_KEY = "266d795c-dab1-4f96-8b1b-efc2a9a4f902"
RESOURCE_ID_CLONE = "seed-icl-2.0"

# API 端点
TRAIN_API = "https://openspeech.bytedance.com/api/v3/tts/voice_clone"
QUERY_API = "https://openspeech.bytedance.com/api/v3/tts/get_voice"
WS_URL = "wss://openspeech.bytedance.com/api/v3/tts/bidirection"

# ============ 协议常量（不用改） ============
PROTOCOL_VERSION = 0b0001
DEFAULT_HEADER_SIZE = 0b0001
FULL_CLIENT_REQUEST = 0b0001
AUDIO_ONLY_RESPONSE = 0b1011
MsgTypeFlagWithEvent = 0b100
JSON_SERIAL = 0b0001
COMPRESSION_NO = 0b0000
EVENT_StartSession = 100
EVENT_FinishSession = 102
EVENT_SessionStarted = 150
EVENT_SessionFinished = 152
EVENT_SessionFailed = 153
EVENT_TaskRequest = 200
EVENT_TTSSentenceStart = 350
EVENT_TTSSentenceEnd = 351
EVENT_TTSResponse = 352
EVENT_NONE = 0


def make_header(message_type, flags, serial_method):
    return bytes([
        (PROTOCOL_VERSION << 4) | DEFAULT_HEADER_SIZE,
        (message_type << 4) | flags,
        (serial_method << 4) | COMPRESSION_NO,
        0
    ])


def make_optional(event, session_id=None):
    data = bytearray()
    data.extend(event.to_bytes(4, "big", signed=True))
    if session_id is not None:
        sid_bytes = session_id.encode()
        data.extend(len(sid_bytes).to_bytes(4, "big", signed=True))
        data.extend(sid_bytes)
    return bytes(data)


def make_message(header, optional, payload_str):
    msg = bytearray(header)
    msg.extend(optional)
    payload = payload_str.encode()
    msg.extend(len(payload).to_bytes(4, "big", signed=True))
    msg.extend(payload)
    return bytes(msg)


def parse_response(res):
    num = 0b00001111
    msg_type = (res[1] >> 4) & num
    offset = 4
    event = EVENT_NONE
    session_id = None
    payload = None
    flags = res[1] & 0x0F

    if flags == MsgTypeFlagWithEvent:
        event = int.from_bytes(res[offset:8], "big", signed=True)
        offset += 4
        if event == EVENT_NONE:
            return msg_type, event, session_id, payload
        elif event in [EVENT_SessionStarted, EVENT_SessionFailed, EVENT_SessionFinished]:
            size = int.from_bytes(res[offset:offset+4], "big", signed=True)
            offset += 4
            session_id = res[offset:offset+size].decode('utf-8')
            offset += size
            size = int.from_bytes(res[offset:offset+4], "big", signed=True)
            offset += 4
            offset += size
        else:
            size = int.from_bytes(res[offset:offset+4], "big", signed=True)
            offset += 4
            session_id = res[offset:offset+size].decode('utf-8')
            offset += size
            size = int.from_bytes(res[offset:offset+4], "big", signed=True)
            offset += 4
            payload = res[offset:offset+size]
            offset += size

    return msg_type, event, session_id, payload


def get_headers():
    """新版控制台的统一鉴权头"""
    return {
        "Content-Type": "application/json",
        "X-Api-Key": API_KEY,
        "X-Api-Resource-Id": RESOURCE_ID_CLONE,
        "X-Api-Request-Id": str(uuid.uuid4()),
    }


# ==========================================
# 1. 注册/训练音色
# ==========================================
def train_voice():
    print(f"\n{'='*50}")
    print(f"[Step 1] TRAIN - Register Voice")
    print(f"  Speaker ID: {SPEAKER_ID}")
    print(f"  Audio file: {AUDIO_FILE}")
    print(f"{'='*50}")

    with open(AUDIO_FILE, "rb") as f:
        audio_data = base64.b64encode(f.read()).decode("utf-8")

    audio_format = "wav" if AUDIO_FILE.lower().endswith(".wav") else "pcm"

    # 新版API：简化的请求体，不需要extra_params
    payload = {
        "speaker_id": SPEAKER_ID,
        "audio": {
            "data": audio_data,
            "format": audio_format
        }
    }

    print(f"  Audio format: {audio_format}")
    print(f"  Audio size: {len(audio_data)} chars (base64)")
    print(f"  Headers: X-Api-Key + X-Api-Resource-Id={RESOURCE_ID_CLONE}")
    print(f"  Sending to: {TRAIN_API}")

    try:
        resp = requests.post(TRAIN_API, headers=get_headers(), json=payload, timeout=60)
        print(f"  Response: {resp.status_code}")
        print(f"  Body: {resp.text}")

        if resp.status_code == 200:
            print(f"\n  [OK] Training request submitted!")
        else:
            print(f"\n  [FAIL] {resp.status_code}")
    except Exception as e:
        print(f"  [ERROR] {e}")


# ==========================================
# 2. 查询训练状态
# ==========================================
def query_voice():
    print(f"\n{'='*50}")
    print(f"[Step 2] QUERY - Check Training Status")
    print(f"  Speaker ID: {SPEAKER_ID}")
    print(f"  Endpoint: {QUERY_API}")
    print(f"{'='*50}")

    payload = {"speaker_id": SPEAKER_ID}

    try:
        resp = requests.post(QUERY_API, headers=get_headers(), json=payload, timeout=10)
        print(f"  Response: {resp.status_code}")
        print(f"  Body: {resp.text}")

        if resp.status_code == 200:
            result = resp.json()
            status = result.get("speaker_status", result.get("status", -1))
            status_map = {0: "Not Found", 1: "Training...", 2: "SUCCESS - Ready!", 3: "Failed", 4: "Active - Ready!"}
            print(f"\n  Status: {status} = {status_map.get(status, 'Unknown')}")
            if status in [2, 4]:
                print(f"  Voice is ready to use!")
            return status
        else:
            print(f"  [FAIL] {resp.status_code}")
            return -1
    except Exception as e:
        print(f"  [ERROR] {e}")
        return -1


# ==========================================
# 3. 用克隆的声音合成测试
# ==========================================
async def test_voice():
    session_id = uuid.uuid4().hex
    output_file = f"test_clone_{SPEAKER_ID}.wav"

    print(f"\n{'='*50}")
    print(f"[Step 3] TEST - Synthesize with Cloned Voice")
    print(f"  Speaker ID: {SPEAKER_ID}")
    print(f"  Text: {TEST_TEXT}")
    print(f"  Output: {output_file}")
    print(f"{'='*50}")

    ws_header = {
        "X-Api-Key": API_KEY,
        "X-Api-Resource-Id": RESOURCE_ID_CLONE,
        "X-Api-Connect-Id": str(uuid.uuid4()),
    }

    audio_data = bytearray()

    try:
        ws = await websockets.connect(WS_URL, additional_headers=ws_header, max_size=1000000000)
        print("  [OK] WebSocket connected")

        # StartSession
        req_params = {
            "text": "",
            "speaker": SPEAKER_ID,
            "audio_params": {"format": "pcm", "sample_rate": 16000, "speech_rate": 0, "loudness_rate": 0},
            "additions": json.dumps({})
        }
        payload_json = json.dumps({
            "user": {"uid": "test"}, "event": EVENT_StartSession,
            "namespace": "BidirectionalTTS", "req_params": req_params
        }, ensure_ascii=False)

        header = make_header(FULL_CLIENT_REQUEST, MsgTypeFlagWithEvent, JSON_SERIAL)
        optional = make_optional(EVENT_StartSession, session_id)
        await ws.send(make_message(header, optional, payload_json))

        resp = await asyncio.wait_for(ws.recv(), timeout=10)
        _, event, _, pl = parse_response(resp)
        print(f"  [RECV] event: {event} (expect 150)")

        if event == EVENT_SessionFailed:
            print(f"  [FAIL] Session failed! {pl.decode('utf-8') if pl else ''}")
            await ws.close()
            return

        # TaskRequest
        task_params = {
            "text": TEST_TEXT, "speaker": SPEAKER_ID,
            "audio_params": {"format": "pcm", "sample_rate": 16000},
            "additions": json.dumps({})
        }
        task_json = json.dumps({
            "user": {"uid": "test"}, "event": EVENT_TaskRequest,
            "namespace": "BidirectionalTTS", "req_params": task_params
        }, ensure_ascii=False)

        header = make_header(FULL_CLIENT_REQUEST, MsgTypeFlagWithEvent, JSON_SERIAL)
        optional = make_optional(EVENT_TaskRequest, session_id)
        await ws.send(make_message(header, optional, task_json))
        print(f"  [SEND] Text: '{TEST_TEXT}'")

        # FinishSession
        header = make_header(FULL_CLIENT_REQUEST, MsgTypeFlagWithEvent, JSON_SERIAL)
        optional = make_optional(EVENT_FinishSession, session_id)
        await ws.send(make_message(header, optional, json.dumps({})))

        # Receive (with timeout)
        while True:
            resp = await asyncio.wait_for(ws.recv(), timeout=30)
            msg_type, event, _, payload = parse_response(resp)
            if event == EVENT_TTSResponse and msg_type == AUDIO_ONLY_RESPONSE:
                audio_data.extend(payload)
            elif event == EVENT_SessionFinished:
                print(f"  [RECV] Session finished")
                break
            elif event == EVENT_SessionFailed:
                print(f"  [FAIL] {payload.decode('utf-8') if payload else ''}")
                break

        await ws.close()

        if audio_data:
            with wave.open(output_file, 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(bytes(audio_data))
            print(f"\n  [OK] Saved: {output_file} ({len(audio_data)} bytes)")
        else:
            print("  [FAIL] No audio data")

    except asyncio.TimeoutError:
        print("  [FAIL] Timeout waiting for response")
    except Exception as e:
        print(f"  [ERROR] {e}")
        import traceback
        traceback.print_exc()


# ==========================================
# Main
# ==========================================
def main():
    print("=" * 50)
    print("TTS 2.0 Voice Clone Tool")
    print("=" * 50)

    if DO_TRAIN:
        train_voice()

    if DO_QUERY:
        if DO_TRAIN:
            print("\n  Waiting 5s for training...")
            time.sleep(5)
        status = query_voice()
        if status == 1:
            print("  Still training, waiting 10s...")
            time.sleep(10)
            query_voice()

    if DO_TEST:
        asyncio.run(test_voice())

    print("\n" + "=" * 50)
    print("Done!")
    print("=" * 50)


if __name__ == "__main__":
    main()
