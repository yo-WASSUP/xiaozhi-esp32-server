"""
阿里百炼 Paraformer 实时语音识别 - 独立测试脚本

测试内容：
  1. WebSocket 连接建立延迟
  2. 实时中间结果 vs 最终结果
  3. sentence_end 语义断句效果
  4. max_sentence_silence 不同值的对比

用法：
  python test_paraformer_realtime.py --silence 200 --multi-threshold --disfluency
  python test_paraformer_realtime.py --silence 800
  python test_paraformer_realtime.py --silence 200 --semantic  --multi-threshold --disfluency  加上semantic后延迟3秒
按 Ctrl+C 停止。
"""

import json
import uuid
import time
import argparse
import asyncio
import websockets
import pyaudio


# ── 颜色 ──────────────────────────────────────────
class C:
    GRAY    = "\033[90m"
    YELLOW  = "\033[93m"
    GREEN   = "\033[92m"
    CYAN    = "\033[96m"
    RED     = "\033[91m"
    BOLD    = "\033[1m"
    RESET   = "\033[0m"


# ── 配置 ──────────────────────────────────────────
API_KEY = "sk-645b09df224e4acc9546a8e2fff39120"
WS_URL  = "wss://dashscope.aliyuncs.com/api-ws/v1/inference"
MODEL   = "paraformer-realtime-v2"
SAMPLE_RATE = 16000
CHUNK_SAMPLES = 3200  # 200ms per chunk (16000 * 0.2)


def parse_args():
    p = argparse.ArgumentParser(description="Paraformer 实时 ASR 测试")
    p.add_argument("--silence", type=int, default=800,
                   help="max_sentence_silence (ms), 默认 800")
    p.add_argument("--semantic", action="store_true",
                   help="启用语义标点 (semantic_punctuation_enabled)")
    p.add_argument("--multi-threshold", action="store_true",
                   help="启用多阈值模式 (multi_threshold_mode_enabled)")
    p.add_argument("--disfluency", action="store_true",
                   help="启用去语气词 (disfluency_removal_enabled)")
    p.add_argument("--key", type=str, default=API_KEY,
                   help="百炼 API Key")
    return p.parse_args()


def build_run_task(args):
    task_id = uuid.uuid4().hex
    msg = {
        "header": {
            "action": "run-task",
            "task_id": task_id,
            "streaming": "duplex",
        },
        "payload": {
            "task_group": "audio",
            "task": "asr",
            "function": "recognition",
            "model": MODEL,
            "parameters": {
                "format": "pcm",
                "sample_rate": SAMPLE_RATE,
                "max_sentence_silence": args.silence,
                "semantic_punctuation_enabled": args.semantic,
                "multi_threshold_mode_enabled": args.multi_threshold,
                "disfluency_removal_enabled": args.disfluency,
                "punctuation_prediction_enabled": True,
                "inverse_text_normalization_enabled": True,
            },
            "input": {},
        },
    }
    return task_id, msg


# ── 统计 ──────────────────────────────────────────
class Stats:
    def __init__(self):
        self.connect_time = 0
        self.task_start_time = 0
        self.sentences = []  # tuple: (text, api_latency_ms)

    def print_summary(self):
        print(f"\n{'='*60}")
        print(f"{C.BOLD}📊 测试统计{C.RESET}")
        print(f"{'='*60}")
        print(f"  WebSocket 连接耗时:  {C.CYAN}{self.connect_time:.0f}ms{C.RESET}")
        print(f"  task-started 耗时:   {C.CYAN}{self.task_start_time:.0f}ms{C.RESET}")
        print(f"  连接总开销:          {C.YELLOW}{self.connect_time + self.task_start_time:.0f}ms{C.RESET}")
        if self.sentences:
            print(f"\n  识别到的完整句子:")
            for i, (text, api_lat) in enumerate(self.sentences, 1):
                lat_color = C.GREEN if api_lat < 1000 else C.YELLOW if api_lat < 2000 else C.RED
                print(f"    {i}. \"{text}\"")
                print(f"       断句延迟: {lat_color}{api_lat:.0f}ms{C.RESET}")
            api_latencies = [lat for _, lat in self.sentences if lat > 0]
            if api_latencies:
                avg = sum(api_latencies) / len(api_latencies)
                mn = min(api_latencies)
                mx = max(api_latencies)
                print(f"\n  API断句延迟 (音频实际说话结束 → 收到完整句子):")
                print(f"    平均: {C.CYAN}{avg:.0f}ms{C.RESET}  "
                      f"最小: {C.GREEN}{mn:.0f}ms{C.RESET}  "
                      f"最大: {C.RED}{mx:.0f}ms{C.RESET}")
        print(f"{'='*60}")


# ── 主逻辑 ──────────────────────────────────────────
async def main():
    args = parse_args()

    print(f"\n{C.BOLD}🎤 Paraformer 实时 ASR 测试{C.RESET}")
    print(f"{'─'*60}")
    print(f"  模型:              {MODEL}")
    print(f"  max_sentence_silence: {C.YELLOW}{args.silence}ms{C.RESET}")
    print(f"  语义标点:          {'✅ 开启' if args.semantic else '❌ 关闭'}")
    print(f"  多阈值模式:        {'✅ 开启' if args.multi_threshold else '❌ 关闭'}")
    print(f"  去语气词:          {'✅ 开启' if args.disfluency else '❌ 关闭'}")
    print(f"{'─'*60}")
    print(f"  对着麦克风说话，观察识别效果。按 Ctrl+C 停止。\n")
    print(f"  {C.GRAY}注: 断句延迟 = 收到结果时刻 - API检测到语音波形结束的时刻{C.RESET}\n")

    stats = Stats()

    # ── 建立连接 ──
    t0 = time.monotonic()
    headers = {"Authorization": f"Bearer {args.key}"}

    try:
        ws = await websockets.connect(
            WS_URL,
            additional_headers=headers,
            max_size=1_000_000_000,
            ping_interval=None,
            ping_timeout=None,
            close_timeout=5,
        )
    except Exception as e:
        print(f"{C.RED}连接失败: {e}{C.RESET}")
        return

    t1 = time.monotonic()
    stats.connect_time = (t1 - t0) * 1000
    print(f"  {C.GREEN}✓ WebSocket 连接建立{C.RESET}  耗时: {C.CYAN}{stats.connect_time:.0f}ms{C.RESET}")

    # ── 发送 run-task ──
    task_id, run_msg = build_run_task(args)
    await ws.send(json.dumps(run_msg, ensure_ascii=False))
    print(f"  {C.GRAY}→ 已发送 run-task (task_id: {task_id[:12]}...){C.RESET}")

    # 等待 task-started
    server_ready = False
    while not server_ready:
        resp = await ws.recv()
        data = json.loads(resp)
        event = data.get("header", {}).get("event", "")
        if event == "task-started":
            t2 = time.monotonic()
            stats.task_start_time = (t2 - t1) * 1000
            server_ready = True
            print(f"  {C.GREEN}✓ 服务器就绪{C.RESET}          耗时: {C.CYAN}{stats.task_start_time:.0f}ms{C.RESET}")
            print(f"\n{'─'*60}")
            print(f"  {C.BOLD}开始实时识别... 请说话{C.RESET}\n")
        elif event == "task-failed":
            err = data.get("header", {}).get("error_message", "未知错误")
            print(f"  {C.RED}✗ 任务启动失败: {err}{C.RESET}")
            await ws.close()
            return

    # ── 开麦录音 ──
    pa = pyaudio.PyAudio()
    stream = pa.open(
        format=pyaudio.paInt16,
        channels=1,
        rate=SAMPLE_RATE,
        input=True,
        frames_per_buffer=CHUNK_SAMPLES,
    )

    stop_event = asyncio.Event()
    sentence_count = 0

    # ── 关键时间锚点 ──
    # audio_stream_start: 第一个音频数据发送的wall-clock时间
    # API返回的 end_time(ms) 是相对于音频流开始的偏移
    # 所以: 语音结束的wall-clock = audio_stream_start + end_time/1000
    audio_stream_start = time.monotonic()

    # ── 发送音频的协程 ──
    async def send_audio():
        loop = asyncio.get_event_loop()
        try:
            while not stop_event.is_set():
                data = await loop.run_in_executor(
                    None, stream.read, CHUNK_SAMPLES, False
                )
                try:
                    await ws.send(data)
                except websockets.ConnectionClosed:
                    break
        except Exception as e:
            if not stop_event.is_set():
                print(f"  {C.RED}发送错误: {e}{C.RESET}")

    # ── 接收结果的协程 ──
    async def recv_results():
        nonlocal sentence_count
        try:
            while not stop_event.is_set():
                try:
                    resp = await asyncio.wait_for(ws.recv(), timeout=0.5)
                except asyncio.TimeoutError:
                    continue

                recv_time = time.monotonic()  # 收到消息的精确时刻
                data = json.loads(resp)
                header = data.get("header", {})
                payload = data.get("payload", {})
                event = header.get("event", "")

                if event == "result-generated":
                    output = payload.get("output", {})
                    sentence = output.get("sentence", {})

                    text = sentence.get("text", "")
                    sentence_end = sentence.get("sentence_end", False)
                    begin_time = sentence.get("begin_time")
                    end_time = sentence.get("end_time")

                    is_final = sentence_end and end_time is not None
                    now = time.strftime("%H:%M:%S")

                    if is_final:
                        sentence_count += 1

                        # API的 end_time 是音频中语音结束的时间点(ms偏移)
                        # 语音结束的wall-clock = audio_stream_start + end_time/1000
                        # 断句延迟 = 收到结果时刻 - 语音结束的wall-clock
                        speech_end_wallclock = audio_stream_start + (end_time / 1000.0)
                        api_latency_ms = (recv_time - speech_end_wallclock) * 1000

                        stats.sentences.append((text, api_latency_ms))

                        print(f"\r{' ' * 100}\r", end="")
                        api_color = C.GREEN if api_latency_ms < 1000 else C.YELLOW if api_latency_ms < 2000 else C.RED
                        print(
                            f"  {C.GREEN}[{now}] 句{sentence_count} ✅{C.RESET} "
                            f"\"{C.BOLD}{text}{C.RESET}\"\n"
                            f"        {C.GRAY}音频区间: {begin_time}ms ~ {end_time}ms{C.RESET} | "
                            f"延迟: {api_color}{api_latency_ms:.0f}ms{C.RESET}"
                        )
                    else:
                        # 中间结果：同一行覆盖刷新
                        display = text if text else "..."
                        print(
                            f"\r  {C.YELLOW}[{now}] 听到:{C.RESET} "
                            f"\"{display}\"    ",
                            end="", flush=True
                        )

                elif event == "task-finished":
                    print(f"\n  {C.GRAY}任务已完成{C.RESET}")
                    stop_event.set()
                    break

                elif event == "task-failed":
                    err_msg = header.get("error_message", "")
                    print(f"\n  {C.RED}任务失败: {err_msg}{C.RESET}")
                    stop_event.set()
                    break

        except websockets.ConnectionClosed:
            if not stop_event.is_set():
                print(f"\n  {C.GRAY}连接已关闭{C.RESET}")
        except Exception as e:
            if not stop_event.is_set():
                print(f"\n  {C.RED}接收错误: {e}{C.RESET}")

    # ── 运行 ──
    try:
        await asyncio.gather(send_audio(), recv_results())
    except KeyboardInterrupt:
        pass
    finally:
        print(f"\n\n  ⏹️  停止录音")
        stop_event.set()
        stream.stop_stream()
        stream.close()
        pa.terminate()

        # 发送 finish-task
        try:
            finish_msg = {
                "header": {
                    "action": "finish-task",
                    "task_id": task_id,
                    "streaming": "duplex",
                },
                "payload": {"input": {}},
            }
            await ws.send(json.dumps(finish_msg))
            await asyncio.sleep(0.2)
            await ws.close()
        except Exception:
            pass

        stats.print_summary()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n退出")
