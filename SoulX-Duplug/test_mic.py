"""
SoulX-Duplug 麦克风实时测试脚本（多线程版）
录音线程独立运行，不会因为网络延迟导致音频卡顿。
按 Ctrl+C 退出，自动保存录音为 WAV 文件。
"""

import json
import base64
import uuid
import wave
import time
import threading
import queue
import numpy as np
import websocket
import pyaudio

# ---- 配置 ----
SERVER_URL = "ws://localhost:8000/turn"
SAMPLE_RATE = 16000
CHUNK_DURATION_MS = 160
CHUNK_SAMPLES = int(SAMPLE_RATE * CHUNK_DURATION_MS / 1000)  # 2560 samples


def audio_capture_thread(audio_queue, all_frames, stop_event):
    """独立线程：持续采集麦克风音频，不受网络阻塞影响"""
    pa = pyaudio.PyAudio()
    stream = pa.open(
        format=pyaudio.paFloat32,
        channels=1,
        rate=SAMPLE_RATE,
        input=True,
        frames_per_buffer=CHUNK_SAMPLES,
    )

    while not stop_event.is_set():
        try:
            raw = stream.read(CHUNK_SAMPLES, exception_on_overflow=False)
            audio = np.frombuffer(raw, dtype=np.float32)
            all_frames.append(audio.copy())
            audio_queue.put(audio)
        except Exception:
            break

    stream.stop_stream()
    stream.close()
    pa.terminate()


def main():
    session_id = uuid.uuid4().hex
    print(f"[Session] {session_id}")
    print(f"[Server] {SERVER_URL}")
    print(f"[Audio]  {SAMPLE_RATE}Hz, {CHUNK_DURATION_MS}ms/chunk ({CHUNK_SAMPLES} samples)")
    print("=" * 50)

    # 连接 WebSocket
    print("连接服务器...", end=" ")
    ws = websocket.create_connection(SERVER_URL)
    ws.settimeout(2.0)
    print("✓ 已连接")

    # 启动录音线程
    audio_queue = queue.Queue()
    all_frames = []
    stop_event = threading.Event()

    capture_thread = threading.Thread(
        target=audio_capture_thread,
        args=(audio_queue, all_frames, stop_event),
        daemon=True,
    )
    capture_thread.start()

    print("\n🎤 开始录音，对着麦克风说话... (Ctrl+C 退出)")
    print("📁 退出时自动保存录音为 WAV 文件\n")

    try:
        while True:
            # 从队列取音频（录音线程独立采集，不会丢帧）
            try:
                audio = audio_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            # 发送到服务器
            payload = {
                "type": "audio",
                "session_id": session_id,
                "audio": base64.b64encode(audio.tobytes()).decode(),
            }
            ws.send(json.dumps(payload))

            # 接收结果
            try:
                response = ws.recv()
                data = json.loads(response)
                state = data["state"]["state"]

                if state == "idle":
                    pass
                elif state == "nonidle":
                    asr_seg = data["state"].get("asr_segment", "")
                    asr_buf = data["state"].get("asr_buffer", "")
                    print(f"🗣️  说话中 | ASR片段: {asr_seg} | 缓冲: {asr_buf}")
                elif state == "speak":
                    text = data["state"].get("text", "")
                    print(f"✅ 说完了！转录: {text}")
                    print("-" * 40)
                elif state == "blank":
                    pass

            except websocket.WebSocketTimeoutException:
                pass

    except KeyboardInterrupt:
        print("\n\n⏹️  停止录音")
    finally:
        stop_event.set()
        capture_thread.join(timeout=2)
        ws.close()

        # 保存录音
        if all_frames:
            all_audio = np.concatenate(all_frames)
            audio_int16 = (all_audio * 32767).astype(np.int16)
            duration = len(all_audio) / SAMPLE_RATE

            filename = f"recording_{time.strftime('%H%M%S')}.wav"
            with wave.open(filename, "w") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(SAMPLE_RATE)
                wf.writeframes(audio_int16.tobytes())

            print(f"💾 录音已保存: {filename} ({duration:.1f}秒)")

        print("已断开连接")


if __name__ == "__main__":
    main()
