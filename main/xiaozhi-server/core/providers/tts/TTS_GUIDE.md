# TTS 语音合成模块代码解读

> 本文解读 `base.py`（TTS 基类）及所有 21 个提供者实现，分析三种流式模式的差异和低延迟策略。

---

## 一、TTS 整体架构

```
core/providers/tts/
├── base.py                    # 抽象基类（487 行，最复杂的基类）
├── dto/dto.py                 # 数据传输对象（SentenceType, ContentType, InterfaceType）
│
├── 非流式 (NON_STREAM) ────────
│   ├── edge.py                # Microsoft Edge TTS（免费，无需 API Key）
│   ├── openai.py              # OpenAI TTS API
│   ├── doubao.py              # 豆包 TTS
│   ├── cozecn.py              # Coze.cn TTS
│   ├── siliconflow.py         # SiliconFlow CosyVoice2
│   ├── aliyun.py              # 阿里云 TTS（非流式）
│   ├── tencent.py             # 腾讯云 TTS
│   ├── ttson.py               # TTSON 角色语音
│   ├── fishspeech.py          # Fish Speech（支持参考音频克隆）
│   ├── gpt_sovits_v2.py       # GPT-SoVITS V2（本地部署）
│   ├── gpt_sovits_v3.py       # GPT-SoVITS V3（本地部署）
│   ├── paddle_speech.py       # PaddleSpeech（WebSocket 批量）
│   ├── custom.py              # 通用 HTTP TTS 包装器
│   └── default.py             # 错误占位（未配置时使用）
│
├── 单流式 (SINGLE_STREAM) ─────
│   ├── linkerai.py            # LinkerAI 流式 TTS
│   └── index_stream.py        # Index TTS 流式
│
└── 双流式 (DUAL_STREAM) ───────
    ├── aliyun_stream.py       # 阿里云 CosyVoice 大模型（WebSocket）
    ├── xunfei_stream.py       # 讯飞 TTS（WebSocket）
    ├── alibl_stream.py        # 阿里百炼 CosyVoice（WebSocket）
    ├── huoshan_double_stream.py  # 火山引擎双流式（WebSocket）
    └── minimax_httpstream.py  # MiniMax HTTP 流式
```

### 三种接口类型（`dto/dto.py`）

| 类型 | 说明 | 首音延迟 | 工作方式 |
|------|------|----------|----------|
| `NON_STREAM` | 整句合成后返回 | 1-3s | 文本→API→完整音频→Opus编码→发送 |
| `SINGLE_STREAM` | HTTP 流式返回 PCM | 500ms-1s | 文本→HTTP GET→PCM 流→逐帧 Opus 编码→发送 |
| `DUAL_STREAM` | WebSocket 双向流 | **200-500ms** | 建立连接→发送文本→持续接收 PCM→逐帧编码→发送 |

---

## 二、`dto/dto.py` — 数据传输对象

```python
class SentenceType(Enum):
    FIRST = "FIRST"      # 一轮对话的第一句
    MIDDLE = "MIDDLE"     # 中间的句子/音频帧
    LAST = "LAST"         # 最后一句（触发结束处理）

class ContentType(Enum):
    TEXT = "TEXT"          # 文本内容（需要合成）
    FILE = "FILE"         # 音频文件（直接播放）
    ACTION = "ACTION"     # 动作标记（开始/结束信号）

class InterfaceType(Enum):
    DUAL_STREAM = "DUAL_STREAM"        # 双流式 WebSocket
    SINGLE_STREAM = "SINGLE_STREAM"    # 单流式 HTTP
    NON_STREAM = "NON_STREAM"          # 非流式

class TTSMessageDTO:
    sentence_id: str              # 会话 ID
    sentence_type: SentenceType   # 句子阶段
    content_type: ContentType     # 内容类型
    content_detail: Optional[str] # 文本内容
    content_file: Optional[str]   # 文件路径
```

---

## 三、`base.py` 深入解读（487 行）

这是项目中最复杂的基类，负责 **文本分段 → TTS 合成 → Opus 编码 → 音频发送** 的完整流水线。

### 3.1 初始化（第 32-71 行）

```python
class TTSProviderBase(ABC):
    def __init__(self, config, delete_audio_file):
        self.interface_type = InterfaceType.NON_STREAM
        self.tts_text_queue = queue.Queue()    # 文本输入队列
        self.tts_audio_queue = queue.Queue()   # 音频输出队列
        self.tts_audio_first_sentence = True   # 首句标记

        # 标点分段配置
        self.punctuations = ("。", "？", "?", "！", "!", "；", ";", "：")
        self.first_sentence_punctuations = ("，", "~", "、", ",", "。", "？", ...)
        # 首句用更多标点分段（逗号也算），后续句用更少标点
```

**为什么首句用更多标点？** 加速首音输出。首句遇到第一个逗号就立即送去合成，让用户更快听到声音；后续句用句号等大标点分段，减少 API 调用次数。

### 3.2 双线程架构（第 261-280 行）

```python
async def open_audio_channels(self, conn):
    self.conn = conn
    # 创建 Opus 编码器（按客户端采样率）
    self.opus_encoder = OpusEncoderUtils(
        sample_rate=conn.sample_rate, channels=1, frame_size_ms=60
    )

    # 线程 1：文本处理线程（文本→TTS合成→Opus编码）
    self.tts_priority_thread = threading.Thread(
        target=self.tts_text_priority_thread, daemon=True
    )
    # 线程 2：音频播放线程（Opus包→WebSocket发送）
    self.audio_play_priority_thread = threading.Thread(
        target=self._audio_play_priority_thread, daemon=True
    )
```

**两个队列串联两个线程：**
```
LLM 输出文本
    ↓
tts_text_queue ← TTSMessageDTO(TEXT, "你好世界")
    ↓
[线程1: tts_text_priority_thread]
    ├─ 文本分段
    ├─ to_tts_stream() → text_to_speak()
    ├─ 音频→Opus编码
    └─ handle_opus() → tts_audio_queue.put()
            ↓
tts_audio_queue ← (SentenceType.MIDDLE, opus_bytes, None)
            ↓
[线程2: _audio_play_priority_thread]
    └─ sendAudioMessage() → WebSocket 发送
```

### 3.3 文本分段算法（第 401-438 行）

```python
def _get_segment_text(self):
    full_text = "".join(self.tts_text_buff)
    current_text = full_text[self.processed_chars:]

    # 首句用更多标点（逗号也算）
    punctuations_to_use = (
        self.first_sentence_punctuations if self.is_first_sentence
        else self.punctuations
    )

    # 找到最早的标点位置
    for punct in punctuations_to_use:
        pos = current_text.rfind(punct)
        if pos != -1 and (last_punct_pos == -1 or pos < last_punct_pos):
            last_punct_pos = pos

    if last_punct_pos != -1:
        segment_text = current_text[:last_punct_pos + 1]
        self.processed_chars += len(segment_text)
        self.is_first_sentence = False  # 首句之后切换标点集
        return segment_text
    return None  # 还没遇到标点，继续等待
```

**示例：** LLM 逐 token 输出 `"你好，今天天气不错。有什么可以帮你的吗？"`

```
收到 "你好，"  → 首句模式，逗号触发 → 立即合成 "你好"
收到 "今天天气不错。" → 普通模式，句号触发 → 合成 "今天天气不错"
收到 "有什么可以帮你的吗？" → LAST → 处理剩余文本 → 合成
```

### 3.4 非流式 TTS 处理（第 90-152 行）

```python
def to_tts_stream(self, text, opus_handler):
    text = MarkdownCleaner.clean_markdown(text)  # 清理 Markdown 标记
    max_repeat_time = 5                           # 最多重试 5 次

    if self.delete_audio_file:
        # 模式 A：内存中处理（不写文件）
        audio_bytes = asyncio.run(self.text_to_speak(text, None))
        audio_bytes_to_data_stream(
            audio_bytes,
            file_type=self.audio_file_type,   # wav / mp3
            is_opus=True,
            callback=opus_handler,             # → handle_opus() → 队列
            sample_rate=self.conn.sample_rate,
            opus_encoder=self.opus_encoder,
        )
    else:
        # 模式 B：写入文件后处理（保留音频）
        tmp_file = self.generate_filename()
        asyncio.run(self.text_to_speak(text, tmp_file))
        self._process_audio_file_stream(tmp_file, callback=opus_handler)
```

### 3.5 音频播放线程（第 331-388 行）

```python
def _audio_play_priority_thread(self):
    while not self.conn.stop_event.is_set():
        sentence_type, audio_datas, text = self.tts_audio_queue.get(timeout=0.1)

        # 客户端打断 → 跳过
        if self.conn.client_abort:
            continue

        # 首包延迟监控
        if sentence_type == SentenceType.FIRST:
            first_ms = (time.time() - self._tts_first_audio_start_ts) * 1000
            logger.debug(f"TTS首包就绪: {first_ms:.2f}ms")

        # 上报 TTS 数据（用于管理平台统计）
        if sentence_type is not SentenceType.MIDDLE:
            enqueue_tts_report(self.conn, enqueue_text, enqueue_audio)

        # 发送音频到客户端
        asyncio.run_coroutine_threadsafe(
            sendAudioMessage(self.conn, sentence_type, audio_datas, text),
            self.conn.loop,
        )
```

### 3.6 抽象方法

```python
@abstractmethod
async def text_to_speak(self, text, output_file):
    """子类必须实现：将文本转换为音频
    - output_file 为 None 时返回 audio_bytes
    - output_file 有值时写入文件
    """
    pass
```

---

## 四、代表性提供者详解

### 4.1 Edge TTS（`edge.py`）— 免费首选

```python
class TTSProvider(TTSProviderBase):
    def __init__(self, config, delete_audio_file):
        self.voice = config.get("voice")          # zh-CN-XiaoxiaoNeural
        self.audio_file_type = config.get("format", "mp3")

    async def text_to_speak(self, text, output_file):
        communicate = edge_tts.Communicate(text, voice=self.voice)
        if output_file:
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    f.write(chunk["data"])
        else:
            audio_bytes = b""
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_bytes += chunk["data"]
            return audio_bytes
```

**特点：** 免费、无需 API Key、音质好、支持多种中英文音色。使用微软 Edge 的在线 TTS 服务。

**延迟：** 约 500ms-1s（网络延迟 + 合成时间），非流式但内部使用了流式接收。

---

### 4.2 阿里云流式（`aliyun_stream.py`）— 最低延迟

这是项目中 **最复杂的 TTS 提供者**（612 行），也是延迟最低的方案之一。

#### 架构：双流式 WebSocket

```
          ┌─────────────────────────────────────────┐
          │         阿里云 CosyVoice 服务            │
          │  wss://nls-gateway-cn-beijing.../ws/v1  │
          └────────────┬───────────┬────────────────┘
                       ↑           ↓
               发送文本（JSON）   接收音频（PCM bytes）
                       ↑           ↓
          ┌────────────┴───────────┴────────────────┐
          │           WebSocket 连接                  │
          │  ┌─ tts_text_priority_thread  (发送端)   │
          │  └─ _start_monitor_tts_response (接收端) │
          └─────────────────────────────────────────┘
```

#### 三阶段协议

```python
# 阶段1: StartSynthesis（建立会话，设置音色/语速等）
start_request = {
    "header": {"name": "StartSynthesis", "namespace": "FlowingSpeechSynthesizer"},
    "payload": {
        "voice": "longxiaochun",    # CosyVoice 大模型音色
        "format": "pcm",
        "sample_rate": 24000,
        "volume": 50,
        "speech_rate": 0,
        "pitch_rate": 0,
    }
}

# 阶段2: RunSynthesis（发送文本，可多次调用）
run_request = {
    "header": {"name": "RunSynthesis"},
    "payload": {"text": "你好世界"}
}

# 阶段3: StopSynthesis（结束会话）
stop_request = {"header": {"name": "StopSynthesis"}}
```

#### 重写的 `tts_text_priority_thread()`

流式提供者重写了基类的文本处理线程，不再分段合成，而是逐句发送文本到 WebSocket：

```python
def tts_text_priority_thread(self):
    if message.sentence_type == SentenceType.FIRST:
        # 建立 WebSocket 连接 + 启动监听任务
        await self.start_session(self.task_id)

    elif message.content_type == ContentType.TEXT:
        # 直接发送文本到 WebSocket（不分段！）
        await self.text_to_speak(message.content_detail, None)

    if message.sentence_type == SentenceType.LAST:
        # 发送 StopSynthesis，等待所有音频返回
        await self.finish_session(self.task_id)
```

#### 监听响应

```python
async def _start_monitor_tts_response(self):
    while True:
        msg = await self.ws.recv()
        if isinstance(msg, str):  # JSON 控制消息
            event_name = json.loads(msg)["header"]["name"]
            # SynthesisStarted → 标记首包
            # SentenceEnd → 一句话合成完毕
            # SynthesisCompleted → 会话结束
        elif isinstance(msg, bytes):  # PCM 音频数据
            self.opus_encoder.encode_pcm_to_opus_stream(
                msg, False, self.handle_opus  # → tts_audio_queue
            )
```

#### 连接复用

```python
async def _ensure_connection(self):
    if self.ws and time.time() - self.last_active_time < 10:
        return self.ws   # 10 秒内复用连接
    self.ws = await websockets.connect(self.ws_url, ...)
```

**延迟优势：** 文本发送后 200-500ms 就开始收到 PCM 音频流，边收边编码边发送，用户几乎感觉不到等待。

---

### 4.3 其他提供者速览

| 提供者 | 类型 | 特色 | 延迟 |
|--------|------|------|------|
| **openai** | NON_STREAM | tts-1/tts-1-hd，支持多种音色 | 1-2s |
| **doubao** | NON_STREAM | 字节跳动，语速/音调/音量可调 | 1-2s |
| **cozecn** | NON_STREAM | Coze 平台，voice_id 选择音色 | 1-2s |
| **siliconflow** | NON_STREAM | CosyVoice2 模型，音质好 | 1-2s |
| **aliyun** | NON_STREAM | 阿里云批量 TTS，Token 认证 | 1-2s |
| **tencent** | NON_STREAM | 腾讯云，TC3-HMAC 签名 | 1-2s |
| **ttson** | NON_STREAM | 动漫角色语音，情感参数 | 1-2s |
| **fishspeech** | NON_STREAM | 参考音频声音克隆，msgpack 格式 | 2-3s |
| **gpt_sovits_v2/v3** | NON_STREAM | 本地部署，需参考音频 | 2-3s |
| **paddle_speech** | NON_STREAM | PaddleSpeech WebSocket，24kHz | 1-2s |
| **linkerai** | SINGLE_STREAM | HTTP GET 流式，自建 24kHz 编码器 | 500ms-1s |
| **index_stream** | SINGLE_STREAM | HTTP GET 流式，帧缓冲 | 500ms-1s |
| **xunfei_stream** | DUAL_STREAM | 讯飞 WebSocket，HMAC-SHA256 认证 | 200-500ms |
| **alibl_stream** | DUAL_STREAM | 阿里百炼 CosyVoice，60s 连接复用 | 200-500ms |
| **huoshan_double_stream** | DUAL_STREAM | 火山引擎，支持情感/混音 | 200-500ms |
| **minimax_httpstream** | DUAL_STREAM | MiniMax HTTP 流式，发音词典 | 500ms-1s |

---

## 五、音频编码流水线

```
TTS 返回音频（WAV/MP3/PCM）
    ↓
audio_bytes_to_data_stream()          ← 非流式
  或 opus_encoder.encode_pcm_to_opus_stream()  ← 流式
    ↓
PCM 16-bit 归一化
    ↓
按 60ms 切帧（frame_size = sample_rate × 0.06 × 2 bytes）
    例: 24000Hz → 每帧 2880 bytes
    ↓
Opus 编码（每帧→一个 Opus 包，约 80-200 bytes）
    ↓
callback: handle_opus(opus_bytes) → tts_audio_queue
    ↓
sendAudioMessage() → WebSocket / MQTT Gateway → 客户端
```

**发送策略（sendAudioHandle.py）：**
- **预缓冲**：前 5 个 Opus 包立即发送（减少首音延迟）
- **速率控制**：后续包按 60ms 间隔发送（匹配播放速率）
- **打断支持**：`conn.client_abort = True` 时立即停止发送

---

## 六、延迟分析：如何实现最低延迟 TTS？

### 6.1 延迟构成

```
LLM 输出首 token
    ↓
[文本分段等待]    0-500ms（等待标点触发分段）
    ↓
[TTS 合成]        200ms-3s（取决于提供者类型）
    ↓
[Opus 编码]       ~10ms
    ↓
[网络传输]        ~10-50ms
    ↓
用户听到首音
```

### 6.2 各方案首音延迟对比

| 方案 | 首音延迟 | 免费 | 音质 |
|------|----------|------|------|
| **阿里云流式 CosyVoice** | **200-500ms** | 否 | 极好 |
| **火山引擎双流式** | **200-500ms** | 否 | 极好 |
| **讯飞流式** | **200-500ms** | 否 | 好 |
| **阿里百炼流式** | **200-500ms** | 否 | 极好 |
| **LinkerAI 流式** | 500ms-1s | 否 | 好 |
| **Edge TTS** | 500ms-1s | **是** | 好 |
| **MiniMax 流式** | 500ms-1s | 否 | 好 |
| **OpenAI TTS** | 1-2s | 否 | 极好 |
| **GPT-SoVITS 本地** | 2-3s | **是** | 可定制 |

### 6.3 最低延迟策略

#### 策略 1：使用双流式提供者（最有效）

```yaml
TTS:
  AliyunStreamTTS:
    type: aliyun_stream
    voice: longxiaochun
    host: nls-gateway-cn-beijing.aliyuncs.com  # 必须用北京节点
    format: pcm
selected_module:
  TTS: AliyunStreamTTS
```

双流式 WebSocket 在 LLM 输出文本的同时就开始合成音频，不需要等待完整句子。

#### 策略 2：首句快速分段

基类已内置此优化——首句遇到**逗号**就触发合成（`first_sentence_punctuations` 比 `punctuations` 多了 `"，"、"、"、","` 等），后续句用句号等大标点分段。

这意味着 LLM 输出 `"你好，"` 时 TTS 就开始工作了，不用等到句号。

#### 策略 3：预缓冲发送

`sendAudioHandle.py` 已内置此优化——前 5 个 Opus 包（300ms 音频）立即发送，不受速率控制限制。

### 6.4 推荐配置

**追求最低延迟（付费）：**
```
阿里云流式 CosyVoice / 火山引擎双流式
```
预期首音延迟：**200-500ms**

**免费方案中最快：**
```
Edge TTS
```
预期首音延迟：**500ms-1s**，音质好，无需 API Key

**追求音色定制（本地）：**
```
GPT-SoVITS V3 + GPU
```
可以克隆任意音色，但首音延迟较高（2-3s）

---

## 七、完整调用链路

```
connection.chat()
    ↓
LLM 流式输出 token
    ↓
tts.tts_text_queue.put(TTSMessageDTO(TEXT, token))
    ↓
[线程1] tts_text_priority_thread()
    ├─ 非流式：分段 → to_tts_stream() → text_to_speak() → Opus → handle_opus()
    └─ 双流式：text_to_speak() 发送文本到 WebSocket
                ↓ (异步)
        _start_monitor_tts_response() 接收 PCM → Opus → handle_opus()
    ↓
tts_audio_queue.put((MIDDLE, opus_bytes, None))
    ↓
[线程2] _audio_play_priority_thread()
    ↓
sendAudioMessage(conn, sentence_type, audios, text)
    ├─ 首包：记录延迟指标，发送 "start" 信号
    ├─ 音频：预缓冲 5 包 + 速率控制发送
    └─ 末包：发送 "stop" 信号
    ↓
WebSocket → ESP32 客户端播放
```
