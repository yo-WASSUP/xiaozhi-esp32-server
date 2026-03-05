# Intent 意图识别模块代码解读

> 本文解读 `base.py`（意图基类）及三个提供者（nointent / function_call / intent_llm），分析各方案对端到端延迟的影响。

---

## 一、Intent 整体架构

```
core/providers/intent/
├── base.py                    # 抽象基类
├── nointent/nointent.py       # 空实现：跳过意图识别
├── function_call/function_call.py  # 委托给主 LLM 的函数调用
└── intent_llm/intent_llm.py   # 独立 LLM 意图识别（带缓存）
```

### 意图识别在流水线中的位置

```
ESP32 发送音频
    ↓
ASR 语音识别 → 文本
    ↓
intentHandler.handle_user_intent()    ← 意图识别入口
    ├─ 检查退出命令（"退下吧"等硬编码命令）
    ├─ 检查唤醒词
    ├─ function_call 模式 → 直接跳过，返回 False
    └─ intent_llm 模式 → 调用 detect_intent()
           ↓
       process_intent_result()
           ├─ continue_chat → 进入正常 LLM 对话
           ├─ result_for_context → 用时间/日期等上下文直接回答
           ├─ handle_exit_intent → 告别并断开连接
           └─ 其他函数 → 执行工具 → TTS 朗读结果
```

### 工厂注册

```python
# core/utils/intent.py
def create_instance(class_name, *args, **kwargs):
    lib_name = f'core.providers.intent.{class_name}.{class_name}'
    return importlib.import_module(lib_name).IntentProvider(*args, **kwargs)
```

与 LLM 一样，每个提供者是一个文件夹（`intent_llm/intent_llm.py`），导出 `IntentProvider` 类。

---

## 二、`base.py` 解读（34 行）

```python
class IntentProviderBase(ABC):
    def __init__(self, config):
        self.config = config

    def set_llm(self, llm):
        """注入 LLM 实例（intent_llm 模式使用）"""
        self.llm = llm
        model_name = getattr(llm, "model_name", str(llm.__class__.__name__))
        logger.info(f"意图识别设置LLM: {model_name}")

    @abstractmethod
    async def detect_intent(self, conn, dialogue_history, text) -> str:
        """
        检测用户最后一句话的意图
        返回 JSON 字符串，格式为:
          {"function_call": {"name": "continue_chat"}}
          {"function_call": {"name": "handle_exit_intent", "arguments": {...}}}
          {"function_call": {"name": "play_music", "arguments": {...}}}
        """
        pass
```

**核心设计：**
- 只有一个抽象方法 `detect_intent()`
- 返回值统一为 JSON 字符串（`function_call` 格式）
- `set_llm()` 允许注入 LLM，支持独立或共享 LLM 实例

---

## 三、三个提供者详解

### 3.1 `nointent` — 直接跳过（最快）

```python
class IntentProvider(IntentProviderBase):
    async def detect_intent(self, conn, dialogue_history, text) -> str:
        return '{"function_call": {"name": "continue_chat"}}'
```

**行为：** 永远返回 `continue_chat`，所有用户输入直接进入主 LLM 对话。

**延迟：** ~0ms（忽略不计）

**代价：** 不支持任何工具调用（天气、音乐、智能家居等全部不可用）

---

### 3.2 `function_call` — 委托给主 LLM（零额外延迟）

```python
class IntentProvider(IntentProviderBase):
    async def detect_intent(self, conn, dialogue_history, text) -> str:
        return '{"function_call": {"name": "continue_chat"}}'
```

**代码完全相同**，但作用不同！关键在 `intentHandler.py` 中的路由逻辑：

```python
# intentHandler.py:35-37
if conn.intent_type == "function_call":
    # 直接返回 False，跳过意图分析
    # 工具调用由主 LLM 的 response_with_functions() 处理
    return False
```

**工作原理：**
1. Intent 层不做任何事，直接返回 False
2. 主 LLM 调用时带上 `tools` 参数（OpenAI function calling）
3. LLM 自行决定是回复文本还是调用工具
4. 工具调用在 `connection.chat()` 中处理

**延迟：** 意图层 0ms，工具调用延迟合并到主 LLM 的首 token 中

**优势：** 不需要额外 LLM 调用，要求主 LLM 支持原生函数调用（OpenAI、Ollama、Gemini 支持）

---

### 3.3 `intent_llm` — 独立 LLM 意图识别（功能最完整）

这是最复杂的提供者，核心流程如下：

#### 初始化

```python
class IntentProvider(IntentProviderBase):
    def __init__(self, config):
        self.llm = None           # 由 set_llm() 注入
        self.promot = ""          # 系统提示词（懒加载）
        self.cache_manager = cache_manager  # 全局缓存
        self.history_count = 4    # 使用最近 4 条对话历史
```

#### `detect_intent()` 完整流程（第 132-281 行）

```
用户文本输入
    ↓
① 计算缓存键: MD5(device_id + text)
    ↓
② 检查缓存 → 命中则直接返回（~1ms）
    ↓
③ 构建系统提示词（首次调用时，含所有可用工具描述）
   ├─ func_handler.get_functions() → 服务端插件
   ├─ mcp_client.get_available_tools() → MCP 工具
   ├─ 音乐文件名列表 → <musicNames>...</musicNames>
   └─ Home Assistant 设备列表
    ↓
④ 构建用户提示词: 最近 4 条对话 + 当前文本
    ↓
⑤ 调用 LLM（非流式）
   self.llm.response_no_stream(system_prompt, user_prompt)
    ↓
⑥ 正则提取 JSON: re.search(r"\{.*\}", intent)
    ↓
⑦ 解析结果并分类处理
   ├─ result_for_context → 基础信息查询（时间/日期）
   ├─ continue_chat → 清理 tool/function 消息
   └─ 其他 → 记录函数调用意图
    ↓
⑧ 写入缓存 → 返回 JSON 字符串
```

#### 系统提示词（第 29-118 行）

提示词强制 LLM 只返回 JSON，包含：

```
【严格格式要求】你必须只能返回JSON格式！

你是一个意图识别助手。请分析用户的最后一句话...

【重要规则】以下类型的查询返回 result_for_context：
- 询问当前时间 / 今天日期 / 农历 / 所在城市

可用的函数列表：
  函数名: get_weather
  描述: 查询天气
  参数: location (string): 查询地点
  ---
  函数名: play_music
  描述: 播放音乐
  参数: song_name (string): 歌名
  ---
  ...

示例：
  用户: 现在几点了？
  返回: {"function_call": {"name": "result_for_context"}}

  用户: 你好啊
  返回: {"function_call": {"name": "continue_chat"}}

【多指令支持】
  用户: 打开灯并且调高音量
  返回: {"function_calls": [{"name": "light_on"}, {"name": "volume_up"}]}
```

#### `replyResult()` — 工具结果自然语言化（第 120-130 行）

工具执行后，用 LLM 把结果转换为口语回复：

```python
def replyResult(self, text, original_text):
    return self.llm.response_no_stream(
        system_prompt=text,  # 工具返回的原始结果
        user_prompt="请根据以上内容，像人类一样说话的口吻回复用户...用户现在说：" + original_text
    )
```

#### 缓存机制

```python
# 缓存配置
CacheType.INTENT: {
    strategy: TTL_LRU,       # TTL + LRU 双重淘汰
    ttl: 600,                # 10 分钟过期
    max_size: 1000,          # 最多 1000 条
    cleanup_interval: 60     # 每分钟清理
}

# 缓存键 = MD5(设备ID + 用户文本)
# 同一设备说同样的话 → 缓存命中
```

**延迟特征：**
- 缓存命中：~1ms
- 缓存未命中：500-2500ms（主要是 LLM 调用时间）

---

## 四、`intentHandler.py` — 意图处理主入口

### 完整路由逻辑（第 15-45 行）

```python
async def handle_user_intent(conn, text):
    # 1. 预处理：从 JSON 中提取文本（FunASR 返回的结构化结果）
    if text.startswith('{'):
        parsed = json.loads(text)
        text = parsed["content"]
        conn.current_speaker = parsed.get("speaker")

    # 2. 硬编码退出命令检查（如 "退下吧"）
    if await check_direct_exit(conn, filtered_text):
        return True

    # 3. 唤醒词检查
    if await checkWakeupWords(conn, filtered_text):
        return True

    # 4. function_call 模式：直接跳过意图分析
    if conn.intent_type == "function_call":
        return False   # ← 关键：直接进入主 LLM 对话

    # 5. intent_llm 模式：调用 LLM 分析意图
    intent_result = await analyze_intent_with_llm(conn, text)
    return await process_intent_result(conn, intent_result, text)
```

### 意图结果处理（第 78-188 行）

```python
async def process_intent_result(conn, intent_result, original_text):
    intent_data = json.loads(intent_result)
    function_name = intent_data["function_call"]["name"]

    # continue_chat → 正常对话
    if function_name == "continue_chat":
        return False

    # result_for_context → 时间/日期等直接回答
    if function_name == "result_for_context":
        context_prompt = f"当前时间：{current_time}\n今天日期：{today_date}..."
        response = conn.intent.replyResult(context_prompt, original_text)
        speak_txt(conn, response)
        return True

    # 其他函数 → 执行工具
    result = await conn.func_handler.handle_llm_function_call(conn, function_call_data)

    match result.action:
        case Action.RESPONSE:   # 直接朗读工具返回的文本
            speak_txt(conn, result.response)
        case Action.REQLLM:     # 工具结果 → LLM 生成自然语言 → 朗读
            llm_result = conn.intent.replyResult(result.result, original_text)
            speak_txt(conn, llm_result)
        case Action.ERROR:      # 朗读错误信息
            speak_txt(conn, result.result)
```

---

## 五、延迟分析：三种模式对比

### 5.1 端到端延迟对比

```
        ASR结束              用户听到回复
           |                     |
nointent:  |--[LLM TTFT]--[TTS]-|        最快
           |                     |
func_call: |--[LLM+工具 TTFT]---|--[TTS]-|  稍慢（LLM 需考虑工具）
           |                     |
intent_llm:|--[意图LLM]--[工具]--[回复LLM]--[TTS]-|  最慢
```

| 模式 | 意图识别延迟 | 工具调用 | 总额外延迟 | 支持工具 |
|------|-------------|----------|-----------|----------|
| **nointent** | 0ms | 不支持 | 0ms | 否 |
| **function_call** | 0ms | 主 LLM 内 | ~0ms | 是（需 LLM 支持） |
| **intent_llm** | 500-2500ms | 独立执行 | 500-3000ms | 是（任何 LLM） |
| **intent_llm（缓存命中）** | ~1ms | 独立执行 | ~100ms | 是 |

### 5.2 最低延迟推荐

#### 不需要工具调用 → `nointent`

```yaml
selected_module:
  Intent: nointent
```

零额外延迟。所有输入直接进入主 LLM 对话。

#### 需要工具调用 → `function_call`（推荐）

```yaml
selected_module:
  Intent: function_call
Intent:
  function_call:
    type: function_call
    functions:
      - get_weather
      - play_music
```

**前提：** 主 LLM 支持原生函数调用（OpenAI 兼容、Ollama、Gemini）。

**原理：** 工具定义直接传给主 LLM，意图识别和文本生成在同一次 LLM 调用中完成，无额外网络请求。

#### 主 LLM 不支持函数调用 → `intent_llm`

```yaml
selected_module:
  Intent: intent_llm
Intent:
  intent_llm:
    type: intent_llm
    llm: ChatGLMLLM    # 可选：使用独立的快速模型
    functions:
      - get_weather
      - play_music
```

**优化建议：**
- 用小模型做意图识别（如 `glm-4-flash`，免费且快）
- 利用缓存：同一用户重复说"现在几点"不会再调 LLM
- 减少 `history_count`（默认 4）可缩短提示词长度

### 5.3 三种模式的选择决策树

```
你需要工具调用（天气、音乐、智能家居等）吗？
├─ 否 → nointent（最快）
└─ 是 → 你的主 LLM 支持原生 function calling 吗？
    ├─ 是（OpenAI/Ollama/Gemini/智谱/豆包） → function_call（推荐）
    └─ 否（Dify/FastGPT/Coze/AliBL） → intent_llm
```

---

## 六、工具执行架构

意图识别返回函数名后，由统一工具处理器执行：

```
intent 返回: {"function_call": {"name": "get_weather", "arguments": {"location": "北京"}}}
    ↓
func_handler.handle_llm_function_call()
    ↓
tool_manager.execute_tool("get_weather", {"location": "北京"})
    ↓
找到工具类型 → SERVER_PLUGIN
    ↓
plugin_executor.execute() → 调用注册的 Python 函数
    ↓
ActionResponse(action=Action.REQLLM, result="北京今天晴，25°C")
    ↓
intent.replyResult("北京今天晴，25°C", "北京天气怎么样")
    ↓
LLM 生成: "北京今天是晴天，气温 25 度，很适合出门哦！"
    ↓
TTS 朗读
```

### 工具类型

| 类型 | 说明 | 示例 |
|------|------|------|
| `SERVER_PLUGIN` | 服务端 Python 函数 | get_weather, play_music |
| `DEVICE_IOT` | 设备端 IoT 控制 | Home Assistant 设备 |
| `SERVER_MCP` | 服务端 MCP 协议 | MCP 工具服务 |
| `DEVICE_MCP` | 设备端 MCP 协议 | ESP32 端 MCP |
| `MCP_ENDPOINT` | 外部 MCP 端点 | 第三方 MCP 服务 |

### 工具返回动作

| Action | 说明 | 后续处理 |
|--------|------|----------|
| `RESPONSE` | 直接回复用户 | TTS 朗读 `response` |
| `REQLLM` | 需要 LLM 润色 | `result` → LLM → TTS |
| `ERROR` | 执行出错 | TTS 朗读错误信息 |
| `NOTFOUND` | 工具未找到 | TTS 提示未找到 |
| `NONE` | 静默执行 | 不回复用户 |
