"""
SoulX-Duplug 麦克风实时轮次检测测试

用法:
    conda activate soulx-duplug
    python test_turntaking.py

按 Ctrl+C 停止。
"""
import json
import time
import base64
import threading

import numpy as np
import websocket
import pyaudio


# ── 颜色输出 ──────────────────────────────────────
class Colors:
    IDLE    = "\033[90m"   # 灰色
    NONIDLE = "\033[93m"   # 黄色
    SPEAK   = "\033[92m"   # 绿色
    WAIT    = "\033[96m"   # 青色
    BLANK   = "\033[37m"   # 白色
    RESET   = "\033[0m"
    BOLD    = "\033[1m"

STATE_COLORS = {
    "idle":    Colors.IDLE,
    "nonidle": Colors.NONIDLE,
    "speak":   Colors.SPEAK,
    "wait":    Colors.WAIT,
    "blank":   Colors.BLANK,
}

STATE_LABELS = {
    "idle":    "😶 静默",
    "nonidle": "🗣️  说话中",
    "speak":   "✅ 该回复了",
    "wait":    "⏳ 还没说完",
    "blank":   "⬜ 音频不足",
}


# ── 统计 ──────────────────────────────────────────
class Stats:
    def __init__(self):
        self.state_counts = {}
        self.transitions = []
        self.last_state = None
        self.start_time = time.time()
        self.speak_texts = []

    def record(self, state, data):
        self.state_counts[state] = self.state_counts.get(state, 0) + 1
        elapsed = time.time() - self.start_time

        if state != self.last_state:
            self.transitions.append((elapsed, self.last_state, state))
            self.last_state = state

        if state == "speak":
            state_info = data.get("state", data)
            if state_info.get("text"):
                self.speak_texts.append(state_info["text"])

    def print_summary(self):
        print(f"\n{'='*60}")
        print(f"{Colors.BOLD}📊 测试统计{Colors.RESET}")
        print(f"{'='*60}")
        print(f"总耗时: {time.time() - self.start_time:.1f}s")
        print(f"\n状态分布:")
        for state, count in sorted(self.state_counts.items()):
            color = STATE_COLORS.get(state, "")
            label = STATE_LABELS.get(state, state)
            bar = "█" * min(count, 50)
            print(f"  {color}{label:12s}{Colors.RESET} │ {bar} ({count}次)")

        if self.transitions:
            print(f"\n关键状态变化:")
            for elapsed, from_s, to_s in self.transitions:
                if to_s in ("speak", "nonidle", "wait"):
                    from_label = STATE_LABELS.get(from_s, str(from_s))
                    to_color = STATE_COLORS.get(to_s, "")
                    to_label = STATE_LABELS.get(to_s, to_s)
                    print(f"  [{elapsed:6.2f}s] {from_label} → {to_color}{to_label}{Colors.RESET}")

        if self.speak_texts:
            print(f"\n🎯 识别的文本:")
            for text in self.speak_texts:
                print(f"  \"{text}\"")

        print(f"{'='*60}")


# ── 接收线程 ──────────────────────────────────────
def recv_loop(ws, stop_event, stats, start_time):
    while not stop_event.is_set():
        try:
            msg = ws.recv()
            if msg is None:
                continue

            data = json.loads(msg)
            state_info = data.get("state", data)
            state = state_info.get("state", "?")
            elapsed = time.time() - start_time

            stats.record(state, data)

            color = STATE_COLORS.get(state, "")
            label = STATE_LABELS.get(state, state)

            # 只打印非 blank / idle 状态，减少噪音
            if state not in ("blank", "idle"):
                line = f"  [{elapsed:6.2f}s] {color}{label}{Colors.RESET}"
                if state_info.get("asr_segment"):
                    line += f"  📝 \"{state_info['asr_segment']}\""
                if state_info.get("asr_buffer"):
                    line += f"  (缓冲: \"{state_info['asr_buffer']}\")"
                if state_info.get("text"):
                    line += f"  🎯 \"{state_info['text']}\""
                print(line)

        except websocket.WebSocketTimeoutException:
            continue
        except Exception as e:
            if not stop_event.is_set():
                print(f"  [接收错误] {e}")
            break


# ── 主逻辑 ────────────────────────────────────────
def main():
    api_url = "ws://localhost:8000/turn"
    session_id = "mic-test-001"
    chunk_size = 2560  # SoulX-Duplug 的 chunk_size (160ms @ 16kHz)

    print(f"\n{Colors.BOLD}🎤 SoulX-Duplug 麦克风实时测试{Colors.RESET}")
    print(f"📡 地址: {api_url}")
    print(f"📦 每块: {chunk_size} samples ({chunk_size/16000*1000:.0f}ms)")
    print(f"\n对着麦克风说话，观察状态变化。按 Ctrl+C 停止。")
    print(f"{'─'*60}\n")

    ws = websocket.create_connection(api_url)
    ws.settimeout(5.0)

    stats = Stats()
    stop_event = threading.Event()
    start_time = time.time()
    recv_thread = threading.Thread(
        target=recv_loop, args=(ws, stop_event, stats, start_time), daemon=True
    )
    recv_thread.start()

    pa = pyaudio.PyAudio()
    stream = pa.open(
        format=pyaudio.paFloat32,
        channels=1,
        rate=16000,
        input=True,
        frames_per_buffer=chunk_size,
    )

    try:
        while True:
            data = stream.read(chunk_size, exception_on_overflow=False)
            audio = np.frombuffer(data, dtype=np.float32)

            payload = {
                "type": "audio",
                "session_id": session_id,
                "audio": base64.b64encode(audio.tobytes()).decode(),
            }
            ws.send(json.dumps(payload))

    except KeyboardInterrupt:
        print("\n\n⏹️  停止录音")
    finally:
        stream.stop_stream()
        stream.close()
        pa.terminate()
        stop_event.set()
        recv_thread.join(timeout=2.0)
        ws.close()

    stats.print_summary()


if __name__ == "__main__":
    main()
