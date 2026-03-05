# VAD 语音活动检测模块代码解读

> 本文解读 `base.py`（VAD 基类）和 `silero.py`（Silero VAD 实现），分析 VAD 的检测算法及其对端到端延迟的影响。

---

## 一、VAD 整体架构

```
core/providers/vad/
├── base.py       # 抽象基类（10 行）
└── silero.py     # Silero VAD 实现（唯一的提供者）
```

VAD 目前只有一个实现——Silero VAD，基于 PyTorch 的轻量级模型。

### VAD 在流水线中的位置

```
ESP32 发送 Opus 音频包（每包 60ms）
    ↓
WebSocket 接收 → asr_audio_queue
    ↓
handleAudioMessage(conn, audio)
    ↓
conn.vad.is_vad(conn, audio)     ← VAD 检测
    ↓
返回 have_voice（是否有人声）
    ↓
conn.asr.receive_audio(conn, audio, have_voice)
    ├─ 无声音：只保留最后 10 帧缓冲
    ├─ 有声音：缓存音频
    └─ 声音停止（client_voice_stop）：触发 ASR 识别
```

**VAD 决定了"什么时候开始听"和"什么时候说完了"——它直接影响用户的感知延迟。**

---

## 二、`base.py` 解读（10 行）

```python
class VADProviderBase(ABC):
    @abstractmethod
    def is_vad(self, conn, data) -> bool:
        """检测音频数据中的语音活动"""
        pass
```

极简接口：
- **输入：** `conn`（连接对象，含 VAD 状态变量）+ `data`（Opus 音频包）
- **输出：** `bool`（当前是否有人声）
- **副作用：** 修改 `conn` 上的多个状态变量（详见下文）

---

## 三、`silero.py` 深入解读

### 3.1 初始化（第 12-37 行）

```python
class VADProvider(VADProviderBase):
    def __init__(self, config):
        # 加载 Silero VAD 模型（本地 PyTorch 模型）
        self.model, _ = torch.hub.load(
            repo_or_dir=config["model_dir"],    # models/snakers4_silero-vad
            source="local",
            model="silero_vad",
            force_reload=False,
        )
        # Opus 解码器：16kHz 采样率，单声道
        self.decoder = opuslib_next.Decoder(16000, 1)

        # 三个核心参数
        self.vad_threshold = 0.5       # 语音置信度上阈值
        self.vad_threshold_low = 0.2   # 语音置信度下阈值（滞回）
        self.silence_threshold_ms = 1000  # 静默多久算"说完了"（毫秒）

        # 滑动窗口：5 帧中至少 3 帧有声才算"有声音"
        self.frame_window_threshold = 3
```

### 3.2 检测算法（第 46-101 行）

`is_vad()` 方法是 VAD 的核心，每收到一个 Opus 包就调用一次：

```
Opus 包（60ms 音频）
    ↓
① Opus 解码 → PCM（960 采样点）
    ↓
② 追加到 client_audio_buffer
    ↓
③ 按 512 采样点（32ms）切分处理
    ↓
④ 每个 chunk → Silero 模型推理 → speech_prob（0.0~1.0）
    ↓
⑤ 双阈值滞回判断
    ↓
⑥ 滑动窗口聚合（5 帧中 ≥3 帧有声 → 确认有声）
    ↓
⑦ 语音停止检测（有声→无声 + 静默超过阈值）
```

#### 第 ① 步：Opus 解码

```python
pcm_frame = self.decoder.decode(opus_packet, 960)   # 960 采样 = 60ms
conn.client_audio_buffer.extend(pcm_frame)
```

#### 第 ② 步：按 512 采样切分

```python
while len(conn.client_audio_buffer) >= 512 * 2:     # 512 采样 × 2 字节
    chunk = conn.client_audio_buffer[:512 * 2]       # 取前 1024 字节
    conn.client_audio_buffer = conn.client_audio_buffer[512 * 2:]
```

每个 chunk = 512 采样 ÷ 16000Hz = **32ms** 音频。

#### 第 ③ 步：模型推理

```python
audio_int16 = np.frombuffer(chunk, dtype=np.int16)
audio_float32 = audio_int16.astype(np.float32) / 32768.0   # 归一化到 [-1, 1]
audio_tensor = torch.from_numpy(audio_float32)

with torch.no_grad():
    speech_prob = self.model(audio_tensor, 16000).item()    # 输出: 0.0 ~ 1.0
```

`speech_prob` 越接近 1.0，越可能是人声。`torch.no_grad()` 禁用梯度计算以加速推理。

#### 第 ④ 步：双阈值滞回判断

```python
if speech_prob >= self.vad_threshold:       # ≥ 0.5 → 确定有声
    is_voice = True
elif speech_prob <= self.vad_threshold_low:  # ≤ 0.2 → 确定无声
    is_voice = False
else:                                        # 0.2 ~ 0.5 → 维持上一帧状态
    is_voice = conn.last_is_voice
```

**为什么用双阈值？** 防止在边界值附近来回抖动。例如 speech_prob 在 0.4~0.6 之间波动时，单阈值（0.5）会导致状态频繁切换，双阈值通过滞回区间（0.2~0.5）保持状态稳定。

```
speech_prob
1.0 ─────────────────
     确定有声音
0.5 ─ ─ ─ ─ ─ ─ ─ ─  ← vad_threshold（上阈值）
     滞回区：维持上一帧状态
0.2 ─ ─ ─ ─ ─ ─ ─ ─  ← vad_threshold_low（下阈值）
     确定无声音
0.0 ─────────────────
```

#### 第 ⑤ 步：滑动窗口聚合

```python
conn.client_voice_window.append(is_voice)   # deque(maxlen=5)
client_have_voice = (
    conn.client_voice_window.count(True) >= self.frame_window_threshold  # ≥ 3
)
```

最近 5 帧中至少 3 帧检测到声音才确认有声。这进一步防止偶发噪声触发误检。

**时间窗口：** 5 帧 × 32ms = **160ms**

#### 第 ⑥ 步：语音停止检测

```python
# 之前有声 → 现在无声
if conn.client_have_voice and not client_have_voice:
    stop_duration = time.time() * 1000 - conn.last_activity_time
    if stop_duration >= self.silence_threshold_ms:    # 默认 200ms 或 1000ms
        conn.client_voice_stop = True                 # 标记：说完了！

# 更新状态
if client_have_voice:
    conn.client_have_voice = True
    conn.last_activity_time = time.time() * 1000      # 记录最后活动时间
```

`client_voice_stop = True` 是触发 ASR 的信号，ASR 基类的 `receive_audio()` 检查到这个标志后启动语音识别。

---

## 四、连接对象上的 VAD 状态变量

每个 WebSocket 连接维护自己的 VAD 状态：

```python
# connection.py 初始化
conn.client_audio_buffer = bytearray()        # PCM 缓冲区
conn.client_have_voice = False                # 当前是否有声音
conn.client_voice_window = deque(maxlen=5)    # 5 帧滑动窗口
conn.last_is_voice = False                    # 上一帧状态（滞回用）
conn.client_voice_stop = False                # 语音停止信号
conn.last_activity_time = 0.0                 # 最后声音活动时间（ms）
conn.first_activity_time = 0.0                # 首次声音活动时间（ms）
```

**状态重置（ASR 开始识别后）：**

```python
def reset_audio_states(self):
    self.client_audio_buffer.clear()
    self.client_have_voice = False
    self.client_voice_stop = False
    self.client_voice_window.clear()
    self.last_is_voice = False
    self.asr_audio.clear()
```

---

## 五、配置参数

```yaml
# config.yaml
VAD:
  SileroVAD:
    type: silero
    threshold: 0.5                  # 上阈值
    threshold_low: 0.3              # 下阈值（滞回下界）
    model_dir: models/snakers4_silero-vad
    min_silence_duration_ms: 200    # 静默多久触发 ASR

selected_module:
  VAD: SileroVAD
```

---

## 六、延迟分析

### 6.1 VAD 内部延迟构成

| 阶段 | 延迟 | 说明 |
|------|------|------|
| Opus 解码 | ~1ms | opuslib_next 硬件加速 |
| 帧缓冲 | ~32ms | 等待凑够 512 采样 |
| 模型推理 | ~5-10ms | PyTorch CPU 推理，512 采样 |
| 滑动窗口确认 | ~160ms | 5 帧 × 32ms |
| **语音开始确认** | **~200ms** | 缓冲 + 窗口 |
| **语音停止确认** | **min_silence_duration_ms** | 可配置 |

### 6.2 `min_silence_duration_ms` 对延迟的影响

这是 **最关键的延迟参数**——用户说完话后，需要等这么久才触发 ASR：

| 值 | 效果 | 适用场景 |
|----|------|----------|
| 100ms | 极快响应，但容易误断句 | 单词级交互 |
| 200ms | 快速响应，偶尔误断 | **推荐低延迟方案** |
| 500ms | 平衡方案 | 一般对话 |
| 1000ms | 保守方案，几乎不误断 | 长句/朗读 |

### 6.3 调参建议

**追求最低延迟：**
```yaml
VAD:
  SileroVAD:
    threshold: 0.4            # 更灵敏的语音检测
    threshold_low: 0.15       # 更灵敏的静音检测
    min_silence_duration_ms: 150   # 150ms 静默就触发
```

**追求稳定准确：**
```yaml
VAD:
  SileroVAD:
    threshold: 0.6            # 更保守，减少噪声误触
    threshold_low: 0.3        # 更保守的静音判断
    min_silence_duration_ms: 500   # 半秒静默才触发
```

---

## 七、完整时序图

```
时间轴 →

用户开始说话                用户停止说话
    |                           |
    v                           v
    |---说话中---...---说话中---|---静默---|
    |                           |         |
    |  [VAD 检测到声音]         |  [VAD 检测到无声]
    |  ~200ms                   |         |
    |                           |  等待 min_silence_duration_ms
    |                           |         |
    |                           |         v
    |                           |  client_voice_stop = True
    |                           |         |
    |  [音频帧持续缓存到        |         v
    |   conn.asr_audio]         |  [触发 ASR 识别]
    |                           |         |
    |                           |         v
    |                           |  [Opus 解码 → PCM]
    |                           |  [ASR 推理]
    |                           |  [意图识别]
    |                           |  [LLM 响应]
    |                           |  [TTS 合成]
    |                           |         |
    |                           |         v
    |                           |  用户听到回复
```

**VAD 贡献的延迟 = 语音停止到触发 ASR 的时间 = `min_silence_duration_ms`**

这是"用户说完话"到"系统开始处理"之间唯一的等待时间，也是最容易优化的参数。

---

## 八、手动模式

```python
# silero.py:48-49
if conn.client_listen_mode == "manual":
    return True   # 跳过 VAD，所有音频直接缓存
```

手动模式下 VAD 完全不生效，所有音频视为有效语音。用户按住按钮说话、松开触发识别，无需 VAD 检测。
