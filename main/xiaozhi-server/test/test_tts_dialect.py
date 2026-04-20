"""
测试豆包TTS 2.0方言功能
正确方式：explicit_dialect 放在 additions 中
"""
import uuid
import json
import asyncio
import wave
import websockets

# ============ 配置 ============
APPID = "2705156243"
ACCESS_TOKEN = "G3YqcRoIW1QzV_wykhec-y-tJVTknJnG"
RESOURCE_ID = "seed-tts-2.0"
WS_URL = "wss://openspeech.bytedance.com/api/v3/tts/bidirection"
SPEAKER = "zh_female_vv_uranus_bigtts"
TEST_TEXT = "你好，今天天气真不错，我们一起出去耍嘛"

# ============ 协议常量 ============
PROTOCOL_VERSION = 0b0001
DEFAULT_HEADER_SIZE = 0b0001
FULL_CLIENT_REQUEST = 0b0001
AUDIO_ONLY_RESPONSE = 0b1011
MsgTypeFlagWithEvent = 0b100
NO_SERIALIZATION = 0b0000
JSON_SERIAL = 0b0001
COMPRESSION_NO = 0b0000

EVENT_NONE = 0
EVENT_StartSession = 100
EVENT_FinishSession = 102
EVENT_SessionStarted = 150
EVENT_SessionFinished = 152
EVENT_SessionFailed = 153
EVENT_TaskRequest = 200
EVENT_TTSSentenceStart = 350
EVENT_TTSSentenceEnd = 351
EVENT_TTSResponse = 352


def make_header(message_type, flags, serial_method=NO_SERIALIZATION):
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
            # read session_id
            size = int.from_bytes(res[offset:offset+4], "big", signed=True)
            offset += 4
            session_id = res[offset:offset+size].decode('utf-8')
            offset += size
            # read response_meta
            size = int.from_bytes(res[offset:offset+4], "big", signed=True)
            offset += 4
            offset += size
        else:
            # read session_id
            size = int.from_bytes(res[offset:offset+4], "big", signed=True)
            offset += 4
            session_id = res[offset:offset+size].decode('utf-8')
            offset += size
            # read payload
            size = int.from_bytes(res[offset:offset+4], "big", signed=True)
            offset += 4
            payload = res[offset:offset+size]
            offset += size

    return msg_type, event, session_id, payload


async def test_dialect(additions_dict, output_file, label):
    session_id = uuid.uuid4().hex
    print(f"\n{'='*60}")
    print(f"[{label}]")
    print(f"additions: {json.dumps(additions_dict, ensure_ascii=False)}")
    print(f"output: {output_file}")
    print(f"{'='*60}")

    ws_header = {
        "X-Api-App-Key": APPID,
        "X-Api-Access-Key": ACCESS_TOKEN,
        "X-Api-Resource-Id": RESOURCE_ID,
        "X-Api-Connect-Id": str(uuid.uuid4()),
    }

    audio_data = bytearray()

    try:
        ws = await websockets.connect(WS_URL, additional_headers=ws_header, max_size=1000000000)
        print("[OK] WebSocket connected")

        # === StartSession ===
        audio_params = {
            "format": "pcm",
            "sample_rate": 16000,
            "speech_rate": 0,
            "loudness_rate": 0,
        }

        req_params = {
            "text": "",
            "speaker": SPEAKER,
            "audio_params": audio_params,
            "additions": json.dumps(additions_dict)
        }

        payload_json = json.dumps({
            "user": {"uid": "test"},
            "event": EVENT_StartSession,
            "namespace": "BidirectionalTTS",
            "req_params": req_params
        }, ensure_ascii=False)

        print(f"\n[SEND] StartSession payload:")
        print(json.dumps(json.loads(payload_json), indent=2, ensure_ascii=False))

        header = make_header(FULL_CLIENT_REQUEST, MsgTypeFlagWithEvent, JSON_SERIAL)
        optional = make_optional(EVENT_StartSession, session_id)
        msg = make_message(header, optional, payload_json)
        await ws.send(msg)

        # wait SessionStarted
        resp = await ws.recv()
        msg_type, event, sid, pl = parse_response(resp)
        print(f"[RECV] event: {event} (expect 150=SessionStarted)")

        if event == EVENT_SessionFailed:
            print(f"[FAIL] Session failed!")
            if pl:
                print(f"  error: {pl.decode('utf-8')}")
            await ws.close()
            return

        # === TaskRequest ===
        task_params = {
            "text": TEST_TEXT,
            "speaker": SPEAKER,
            "audio_params": audio_params,
            "additions": json.dumps(additions_dict)
        }

        task_json = json.dumps({
            "user": {"uid": "test"},
            "event": EVENT_TaskRequest,
            "namespace": "BidirectionalTTS",
            "req_params": task_params
        }, ensure_ascii=False)

        header = make_header(FULL_CLIENT_REQUEST, MsgTypeFlagWithEvent, JSON_SERIAL)
        optional = make_optional(EVENT_TaskRequest, session_id)
        msg = make_message(header, optional, task_json)
        await ws.send(msg)
        print(f"[SEND] TaskRequest: '{TEST_TEXT}'")

        # === FinishSession ===
        header = make_header(FULL_CLIENT_REQUEST, MsgTypeFlagWithEvent, JSON_SERIAL)
        optional = make_optional(EVENT_FinishSession, session_id)
        msg = make_message(header, optional, json.dumps({}))
        await ws.send(msg)
        print("[SEND] FinishSession")

        # === Receive audio ===
        while True:
            resp = await ws.recv()
            msg_type, event, sid, payload = parse_response(resp)

            if event == EVENT_TTSSentenceStart:
                print(f"[RECV] Sentence start")
            elif event == EVENT_TTSResponse and msg_type == AUDIO_ONLY_RESPONSE:
                audio_data.extend(payload)
            elif event == EVENT_TTSSentenceEnd:
                print(f"[RECV] Sentence end")
            elif event == EVENT_SessionFinished:
                print(f"[RECV] Session finished")
                break
            elif event == EVENT_SessionFailed:
                print(f"[FAIL] Session failed!")
                if payload:
                    print(f"  error: {payload.decode('utf-8')}")
                break

        await ws.close()

        if audio_data:
            with wave.open(output_file, 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(bytes(audio_data))
            print(f"[OK] Saved: {output_file} ({len(audio_data)} bytes)")
        else:
            print("[FAIL] No audio data received")

    except Exception as e:
        print(f"[ERROR] {e}")
        import traceback
        traceback.print_exc()


async def main():
    print("=" * 60)
    print("TTS 2.0 Dialect Test")
    print("=" * 60)

    # Test 1: explicit_dialect in additions (correct way per docs)
    await test_dialect(
        additions_dict={
            "explicit_language": "zh",
            "explicit_dialect": "sichuan"
        },
        output_file="test_sichuan_1.wav",
        label="additions: explicit_language=zh + explicit_dialect=sichuan"
    )

    # Test 2: only explicit_dialect in additions
    await test_dialect(
        additions_dict={
            "explicit_dialect": "sichuan"
        },
        output_file="test_sichuan_2.wav",
        label="additions: explicit_dialect=sichuan only"
    )

    # Test 3: no dialect (control group)
    await test_dialect(
        additions_dict={},
        output_file="test_sichuan_3_control.wav",
        label="No dialect (control)"
    )

    print(f"\n{'='*60}")
    print("Done! Compare these files:")
    print("1. test_sichuan_1.wav - explicit_language + explicit_dialect in additions")
    print("2. test_sichuan_2.wav - explicit_dialect only in additions")
    print("3. test_sichuan_3_control.wav - no dialect (control)")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
