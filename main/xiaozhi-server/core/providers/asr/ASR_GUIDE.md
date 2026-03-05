# ASR 语音识别模块代码解读

> 本文聚焦 `base.py`（ASR 基类）和 `fun_local.py`（FunASR 本地推理），并分析如何实现最低延迟的 ASR。

---

## 一、ASR 整体架构

```
core/providers/asr/
├── base.py               # 抽象基类：音频接收、VAD、Opus解码、ASR调度
├── fun_local.py           # FunASR 本地模型（SenseVoiceSmall）
├── fun_server.py          # FunASR 远程服务
├── vosk.py                # VOSK 离线模型
├── sherpa_onnx_local.py   # Sherpa-ONNX 本地模型
├── openai.py              # OpenAI Whisper API
├── aliyun_stream.py       # 阿里云流式 ASR
├── doubao_stream.py       # 豆包流式 ASR
├── xunfei_stream.py       # 讯飞流式 ASR
├── ...                    # 更多云端提供者
├── utils.py               # 标签解析工具（语言/情绪）
└── dto/dto.py             # InterfaceType 枚举
```

### 三种接口类型（`dto/dto.py`）

| 类型 | 说明 | 实例管理 | 典型提供者 |
|------|------|----------|------------|
| `LOCAL` | 本地模型推理 | **全局共享**单实例（省内存） | FunASR, VOSK, Sherpa-ONNX |
| `NON_STREAM` | 一次性发送音频到云端 API | 每连接新建实例 | OpenAI Whisper, 百度 |
| `STREAM` | 实时流式发送音频 | 每连接新建实例（需维护 WebSocket） | 阿里云流式, 讯飞流式 |

### 工厂注册机制

```python
# core/utils/asr.py — 按文件名动态加载
def create_instance(class_name, *args, **kwargs):
    lib_name = f'core.providers.asr.{class_name}'
    return importlib.import_module(lib_name).ASRProvider(*args, **kwargs)
```

配置中 `type: fun_local` → 加载 `fun_local.py` 中的 `ASRProvider` 类。

---

## 二、`base.py` 深入解读

`ASRProviderBase` 是所有 ASR 提供者的基类，负责 **音频接收 → VAD 判断 → Opus 解码 → ASR 调度 → 结果分发** 的完整流水线。

### 2.1 音频通道管理（第 33-55 行）

```python
async def open_audio_channels(self, conn):
    # 启动后台线程，按顺序处理 ASR 音频任务
    conn.asr_priority_thread = threading.Thread(
        target=self.asr_text_priority_thread, args=(conn,), daemon=True
    )
    conn.asr_priority_thread.start()
```

**为什么用独立线程？** 保证 ASR 任务按顺序执行（用 `queue.Queue`），避免并发识别导致结果乱序。线程从 `conn.asr_audio_queue` 中取任务，通过 `asyncio.run_coroutine_threadsafe` 将结果回传到主事件循环。

### 2.2 音频接收与 VAD 检测（第 58-77 行）

```python
async def receive_audio(self, conn, audio, audio_have_voice):
    if conn.client_listen_mode == "manual":
        conn.asr_audio.append(audio)          # 手动模式：只管缓存
    else:
        conn.asr_audio.append(audio)
        # 无声音时只保留最后10帧（作为语音前置缓冲）
        if not audio_have_voice and not conn.client_have_voice:
            conn.asr_audio = conn.asr_audio[-10:]
            return
        # VAD 检测到语音停止 → 触发识别
        if conn.client_voice_stop:
            asr_audio_task = conn.asr_audio.copy()
            conn.reset_audio_states()
            if len(asr_audio_task) > 15:       # 至少15帧才识别（防误触）
                await self.handle_voice_stop(conn, asr_audio_task)
```

**关键设计：**
- **前置缓冲**：无声时保留最后 10 帧，确保语音起始部分不丢失
- **最小帧数**：少于 15 帧视为噪声，跳过识别
- **流式 ASR 特殊处理**：`InterfaceType.STREAM` 不在此触发（它们实时推送音频）

### 2.3 语音停止处理（第 80-175 行）

这是核心方法，处理流程如下：

```
音频帧列表
    ↓
Opus 解码 → PCM 数据
    ↓
┌─────────────────────┐
│ asyncio.gather()    │   ← 并行执行
│  ├─ ASR 识别        │
│  └─ 声纹识别（可选） │
└─────────────────────┘
    ↓
合并结果（文本 + 说话人）
    ↓
过滤标点 & 长度检查
    ↓
startToChat() → 进入对话流程
enqueue_asr_report() → 上报管理平台
```

**性能亮点：** ASR 和声纹识别通过 `asyncio.gather()` 并行执行，避免串行等待。

### 2.4 Opus 解码（第 344-377 行）

```python
@staticmethod
def decode_opus(opus_data: List[bytes]) -> List[bytes]:
    decoder = opuslib_next.Decoder(16000, 1)  # 16kHz, 单声道
    for opus_packet in opus_data:
        pcm_frame = decoder.decode(opus_packet, 960)  # 960采样点 = 60ms
        pcm_data.append(pcm_frame)
    return pcm_data
```

每个 Opus 包解码为 960 个采样点（16kHz 下 = 60ms 音频）。解码后得到 16-bit PCM 数据。

### 2.5 文件管理与 AudioArtifacts（第 219-324 行）

```python
class AudioArtifacts(NamedTuple):
    pcm_frames: List[bytes]    # 解码后的 PCM 帧列表
    pcm_bytes: bytes           # 合并的 PCM 字节（直接喂给模型）
    file_path: Optional[str]   # 持久化 WAV 文件路径
    temp_path: Optional[str]   # 临时 WAV 文件路径（用后即删）
```

`speech_to_text_wrapper()` 是模板方法，统一处理：
1. Opus → PCM 解码
2. 磁盘空间检查
3. 按需生成 WAV 文件（有些提供者需要文件输入，如 OpenAI）
4. 调用子类的 `speech_to_text()`
5. `finally` 块清理临时文件

### 2.6 抽象接口（第 326-342 行）

```python
@abstractmethod
async def speech_to_text(
    self, opus_data, session_id, audio_format="opus", artifacts=None
) -> Tuple[Optional[str], Optional[str]]:
    """子类必须实现：将音频数据转换为文本"""
    pass
```

子类只需实现这一个方法，所有前置/后置处理由基类完成。

---

## 三、`fun_local.py` 深入解读

FunASR 本地推理，使用 `SenseVoiceSmall` 模型，支持语言检测和情绪识别。

### 3.1 初始化（第 40-64 行）

```python
class ASRProvider(ASRProviderBase):
    def __init__(self, config, delete_audio_file):
        # 内存检测：要求 ≥ 2GB
        if psutil.virtual_memory().total < 2 * 1024**3:
            logger.error("内存不足2G，可能无法启动FunASR")

        self.interface_type = InterfaceType.LOCAL  # 全局共享实例
        self.model = AutoModel(
            model=self.model_dir,               # 默认: models/SenseVoiceSmall
            vad_kwargs={"max_single_segment_time": 30000},  # 单段最长30秒
            disable_update=True,                # 禁用自动更新
            hub="hf",                           # 从 HuggingFace 加载
            # device="cuda:0",                  # 取消注释启用 GPU
        )
```

**关键点：**
- `InterfaceType.LOCAL` → 所有连接共享同一个模型实例，节省内存
- `CaptureOutput` 上下文管理器捕获模型加载时的 stdout 输出，转为 logger 日志
- GPU 支持已预留，取消 `device="cuda:0"` 注释即可启用

### 3.2 语音识别（第 66-108 行）

```python
async def speech_to_text(self, opus_data, session_id, audio_format="opus", artifacts=None):
    # 使用 asyncio.to_thread 在线程池中运行，避免阻塞事件循环
    result = await asyncio.to_thread(
        self.model.generate,
        input=artifacts.pcm_bytes,     # 直接传入 PCM 字节数据
        cache={},
        language="auto",               # 自动语言检测
        use_itn=True,                  # 逆文本正则化（数字/日期等）
        batch_size_s=60,               # 批处理窗口60秒
    )
    text = lang_tag_filter(result[0]["text"])  # 解析语言/情绪标签
    return text, artifacts.file_path
```

**数据流：**
```
PCM 字节 → model.generate() → "<|zh|><|HAPPY|><|Speech|><|withitn|>你好"
                                         ↓
                              lang_tag_filter() 解析
                                         ↓
                              {"content": "你好", "language": "zh", "emotion": "🙂"}
```

### 3.3 标签解析（`utils.py`）

FunASR SenseVoice 模型的输出格式为 `<|语种|><|情绪|><|事件|><|选项|>文本内容`：

```python
def lang_tag_filter(text):
    # 提取标签：["zh", "SAD", "Speech", "withitn"]
    all_tags = re.findall(r"<\|([^|]+)\|>", text)
    # 移除标签得到纯文本
    clean_text = re.sub(r"<\|([^|]+)\|>", "", text).strip()
    # 返回结构化结果
    return {
        "content": clean_text,
        "language": all_tags[0],      # 语种
        "emotion": EMOTION_EMOJI_MAP[all_tags[1]],  # 情绪→emoji
    }
```

### 3.4 错误处理

- **重试机制**：`OSError` 最多重试 2 次（间隔 1 秒），应对临时磁盘/文件问题
- **其他异常**：直接返回空字符串，不重试

---

## 四、延迟分析：如何实现最低延迟 ASR？

### 4.1 当前延迟构成

```
客户端录音 → [网络传输] → Opus解码 → [等待VAD语音停止] → ASR推理 → 结果返回
              ~10-50ms      ~5ms          ~300-2000ms        ~???ms
```

最大延迟来自两部分：**VAD 等待时间**和 **ASR 推理时间**。

### 4.2 本地 vs 云端延迟对比

| 方案 | 推理延迟 | 网络延迟 | 总延迟 | 适用场景 |
|------|----------|----------|--------|----------|
| **FunASR 本地（CPU）** | 200-800ms | 0ms | 200-800ms | 通用，无网络依赖 |
| **FunASR 本地（GPU）** | 50-150ms | 0ms | 50-150ms | 有 GPU 的服务器 |
| **云端非流式**（OpenAI等） | 100-300ms | 50-200ms | 150-500ms | 高质量、多语种 |
| **云端流式**（阿里云等） | 实时 | 50-200ms | 50-200ms | 最低感知延迟 |

### 4.3 低延迟优化策略

#### 策略 1：启用 GPU 加速（最简单）

在 `fun_local.py` 中取消注释即可：

```python
self.model = AutoModel(
    model=self.model_dir,
    # ...
    device="cuda:0",  # 启用 GPU
)
```

预期效果：推理延迟从 200-800ms 降到 50-150ms。

#### 策略 2：使用更小的模型

SenseVoiceSmall 已经是较小的模型，但如果只需要中文识别（不需要情绪/语种检测），可以考虑：
- **Sherpa-ONNX**（`sherpa_onnx_local.py`）：ONNX Runtime 推理，启动快、内存占用低
- **VOSK**（`vosk.py`）：轻量级离线模型，适合嵌入式场景

#### 策略 3：流式识别（最低感知延迟）

当前本地 FunASR 是**非流式**的：等语音说完 → 一次性推理。流式方案可以边说边识别：

- **FunASR Server 流式模式**（`fun_server.py`）：部署 FunASR 流式服务，本地网络延迟可忽略
- **阿里云/讯飞流式**（`aliyun_stream.py` / `xunfei_stream.py`）：云端流式，但有网络延迟

#### 策略 4：缩短 VAD 尾部静音时间

VAD 检测到语音停止后才触发识别，VAD 的 `max_single_segment_time` 和静音判断阈值会影响响应速度。可以在 VAD 参数中调整静音持续时间阈值来更快触发识别。

### 4.4 推荐方案

**追求最低延迟的本地方案：**

```
FunASR 本地 + GPU 加速 + 缩短 VAD 静音阈值
```

预期总延迟：**50-200ms**（不含 VAD 等待时间）

**无 GPU 的最优方案：**

```
FunASR Server 流式模式（本地部署）
```

在本地启动 FunASR WebSocket Server，音频实时推送，边说边出结果，感知延迟最低。

---

## 五、代码调用链路总结

```
ESP32 客户端发送 Opus 音频
        ↓
Connection.receive_audio_data()
        ↓
ASRProviderBase.receive_audio()     ← base.py:58
   ├─ 手动模式：缓存音频
   └─ 自动模式：VAD 检测语音停止
        ↓
ASRProviderBase.handle_voice_stop() ← base.py:80
   ├─ decode_opus() → PCM
   ├─ asyncio.gather(ASR, 声纹)     ← 并行
   └─ startToChat() → LLM 对话
        ↓
ASRProviderBase.speech_to_text_wrapper() ← base.py:268
   ├─ 解码 + 磁盘检查 + 文件生成
   └─ 调用子类 speech_to_text()
        ↓
ASRProvider.speech_to_text()        ← fun_local.py:66
   ├─ asyncio.to_thread(model.generate)
   └─ lang_tag_filter() → 结构化结果
```
