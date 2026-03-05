# LLM 大语言模型模块代码解读

> 本文聚焦 `base.py`（LLM 基类）及所有 9 个提供者的实现，分析如何实现最低延迟的 LLM 响应。

---

## 一、LLM 整体架构

```
core/providers/llm/
├── base.py              # 抽象基类：流式响应、函数调用接口
├── system_prompt.py     # 为不支持原生函数调用的提供者生成工具提示词
├── openai/openai.py     # OpenAI 兼容 API（也用于智谱、豆包等）
├── ollama/ollama.py     # Ollama 本地推理
├── gemini/gemini.py     # Google Gemini
├── dify/dify.py         # Dify 平台（RAG/工作流）
├── fastgpt/fastgpt.py   # FastGPT 知识库
├── coze/coze.py         # Coze 平台
├── xinference/          # Xinference 本地/远程推理
├── AliBL/AliBL.py       # 阿里百炼应用平台
└── homeassistant/       # Home Assistant 智能家居
```

### 工厂注册机制

```python
# core/utils/llm.py — 按文件夹名动态加载
def create_instance(class_name, *args, **kwargs):
    lib_name = f'core.providers.llm.{class_name}.{class_name}'
    return importlib.import_module(lib_name).LLMProvider(*args, **kwargs)
```

注意 LLM 与 ASR 不同：每个提供者是一个**文件夹**（如 `openai/openai.py`），而非单文件。

---

## 二、`base.py` 解读（35行，极简设计）

```python
class LLMProviderBase(ABC):
    @abstractmethod
    def response(self, session_id, dialogue):
        """流式生成器 — 逐 token yield 文本"""
        pass

    def response_no_stream(self, system_prompt, user_prompt, **kwargs):
        """非流式封装：内部调用 response() 流式聚合结果"""
        dialogue = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        result = ""
        for part in self.response("", dialogue, **kwargs):
            result += part
        return result

    def response_with_functions(self, session_id, dialogue, functions=None):
        """函数调用接口 — yield (text, tool_calls) 元组"""
        # 默认实现：不支持函数调用的提供者直接返回文本
        for token in self.response(session_id, dialogue):
            yield token, None
```

**核心设计原则：**
- **流式优先**：`response()` 是 generator，逐 token yield，TTS 可以边收边合成
- **三个接口**：普通对话 / 非流式封装 / 函数调用
- **子类只需实现 `response()`**，函数调用可选覆盖

---

## 三、各提供者详解

### 3.1 OpenAI 兼容（`openai/openai.py`）— 最通用

**用途：** 不仅用于 OpenAI，也用于智谱 ChatGLM、豆包、DeepSeek 等所有兼容 OpenAI API 的服务。

```python
class LLMProvider(LLMProviderBase):
    def __init__(self, config):
        self.client = openai.OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,       # 切换不同服务只需改 URL
            timeout=httpx.Timeout(300)
        )
        # 可配参数：temperature, max_tokens, top_p, frequency_penalty

    def response(self, session_id, dialogue, **kwargs):
        responses = self.client.chat.completions.create(
            model=self.model_name, messages=dialogue, stream=True
        )
        is_active = True
        for chunk in responses:
            content = chunk.choices[0].delta.content
            # 过滤 <think>...</think> 标签（推理模型的思考过程）
            if "<think>" in content: is_active = False
            if "</think>" in content: is_active = True
            if is_active:
                yield content
```

**函数调用：** 原生支持，`response_with_functions()` 传入 `tools` 参数，流式返回 `(content, tool_calls)` 元组。

**延迟特征：** 取决于后端服务，首 token 延迟（TTFT）通常 100-300ms。

---

### 3.2 Ollama（`ollama/ollama.py`）— 本地推理

**用途：** 本地运行开源模型（Qwen、Llama、Mistral 等），无需网络。

```python
class LLMProvider(LLMProviderBase):
    def __init__(self, config):
        self.base_url = config.get("base_url", "http://localhost:11434")
        if not self.base_url.endswith("/v1"):
            self.base_url = f"{self.base_url}/v1"
        self.client = OpenAI(base_url=self.base_url, api_key="ollama")
        # Qwen3 特殊检测
        self.is_qwen3 = self.model_name.lower().startswith("qwen3")
```

**Qwen3 优化：** 自动在用户消息前添加 `/no_think` 指令，跳过思考过程以降低延迟：

```python
if self.is_qwen3:
    dialogue_copy[i]["content"] = "/no_think " + dialogue_copy[i]["content"]
```

**`<think>` 标签过滤：** 使用缓冲区处理跨 chunk 的标签，比 OpenAI 提供者更复杂：

```python
buffer += content
# 处理完整的 <think>...</think> 对
while "<think>" in buffer and "</think>" in buffer:
    pre = buffer.split("<think>", 1)[0]
    post = buffer.split("</think>", 1)[1]
    buffer = pre + post
# 只在 is_active 且有内容时 yield
if is_active and buffer:
    yield buffer
    buffer = ""
```

**延迟特征：** TTFT 500ms-5s+，取决于模型大小和硬件（GPU vs CPU）。

---

### 3.3 Gemini（`gemini/gemini.py`）— Google 原生

**特色：**
- 使用 Google `generativeai` SDK（非 OpenAI 兼容）
- 代理支持：自动测试 HTTP/HTTPS 代理连通性，支持降级
- 函数调用：原生支持，构建 `FunctionDeclaration` 工具

```python
def _generate(self, dialogue, tools):
    stream = self.model.generate_content(
        contents=contents, tools=tools, stream=True,
        generation_config=GenerationConfig(
            temperature=0.7, top_p=0.9, top_k=40, max_output_tokens=2048
        )
    )
    for chunk in stream:
        for part in chunk.candidates[0].content.parts:
            if getattr(part, "function_call", None):
                yield None, [SimpleNamespace(function=...)]  # 工具调用
            if getattr(part, "text", None):
                yield part.text                               # 文本
```

**延迟特征：** TTFT 200-400ms，需代理访问。

---

### 3.4 Dify（`dify/dify.py`）— RAG/工作流平台

**三种模式：**

| 模式 | 说明 | 流式 |
|------|------|------|
| `chat-messages` | 对话模式，维护会话 ID | SSE 流式 |
| `workflows/run` | 工作流模式 | 等工作流结束才返回 |
| `completion-messages` | 补全模式 | SSE 流式 |

**函数调用：** 不原生支持，通过 `system_prompt.py` 注入工具描述到系统提示词。

```python
# 将函数定义注入到用户消息中
modify_msg = get_system_prompt_for_function(function_str) + last_msg
```

---

### 3.5 其他提供者速览

| 提供者 | 流式 | 函数调用 | 特色 |
|--------|------|----------|------|
| **FastGPT** | SSE | 不支持 | 知识库问答，RAG 专用 |
| **Coze** | SDK | 不支持（提示词模拟） | 维护 session→conversation 映射 |
| **Xinference** | OpenAI兼容 | 支持 | 本地/远程部署灵活 |
| **AliBL** | dashscope | 不支持 | 阿里百炼应用，支持 memory_id |
| **HomeAssistant** | **非流式** | 不支持 | 智能家居场景，单次 HTTP POST |

---

## 四、完整调用链路：ASR → LLM → TTS

```
ESP32 发送音频
    ↓
ASR 语音识别 → 文本
    ↓
intentHandler.handle_user_intent()
    ├─ function_call 模式：LLM 带工具定义 → 可能触发工具调用
    └─ intent_llm 模式：先用意图 LLM 判断 → 再调主 LLM
    ↓
connection.chat(query)
    ├─ 构造 dialogue（系统提示 + 历史 + 记忆）
    ├─ llm.response(session_id, dialogue)     ← 流式 yield
    │     for response in llm_responses:
    │         记录首 token 延迟 (TTFT)
    │         发送文本到 TTS 队列
    └─ TTS 合成 → 音频流发送到客户端
```

**性能监控点：**
```python
# connection.py chat() 方法中
llm_total_start = time.time()
for response in llm_responses:
    if first_token_ms is None:
        first_token_ms = (time.time() - llm_total_start) * 1000
        logger.info(f"LLM首包延迟: {first_token_ms}ms")
```

---

## 五、延迟分析：如何实现最低延迟 LLM？

### 5.1 延迟构成

```
用户说完话
    ↓
[ASR 推理]  200-800ms
    ↓
[意图识别]  0-500ms（可选，function_call 模式无额外延迟）
    ↓
[LLM TTFT]  100ms-5s  ← 最大变量
    ↓
[TTS 首音]  100-500ms
    ↓
用户听到回复
```

**LLM TTFT（首 Token 延迟）** 是整个链路中最大的变量。

### 5.2 各方案延迟对比

| 方案 | TTFT | 网络延迟 | 函数调用 | 适合场景 |
|------|------|----------|----------|----------|
| **豆包/智谱（OpenAI 兼容）** | 100-200ms | 20-50ms | 支持 | **推荐：延迟最低的云端方案** |
| **Gemini Flash** | 200-400ms | 需代理 | 支持 | 多模态、国际化 |
| **Ollama + GPU** | 200-500ms | 0ms | 支持 | 隐私、离线 |
| **Ollama + CPU** | 1-5s+ | 0ms | 支持 | 无 GPU 但需离线 |
| **Dify/FastGPT** | 300-1000ms | 20-100ms | 不支持 | 知识库 RAG |

### 5.3 最低延迟策略

#### 策略 1：选择快速的云端 API（最简单）

豆包和智谱 ChatGLM 的免费额度 + 国内低网络延迟 = TTFT 通常 100-200ms：

```yaml
# config.yaml
LLM:
  DoubaoLLM:
    type: openai
    model_name: doubao-1-5-pro-32k-250115
    base_url: https://ark.cn-beijing.volces.com/api/v3
    api_key: YOUR_KEY

selected_module:
  LLM: DoubaoLLM
```

#### 策略 2：本地 Ollama + GPU + 小模型

选择参数量小的模型（如 Qwen2.5-1.5B / 3B），GPU 推理 TTFT 可达 200ms 以内：

```yaml
LLM:
  OllamaLLM:
    type: ollama
    model_name: qwen2.5:3b   # 小模型 = 低延迟
    base_url: http://localhost:11434
```

**Qwen3 注意事项：** 项目已内置 `/no_think` 优化，自动跳过思考链，避免不必要的延迟。

#### 策略 3：跳过意图识别

意图识别（intent）会在 ASR 之后、主 LLM 之前增加 100-500ms：

```yaml
selected_module:
  Intent: nointent        # 跳过意图识别，直接进入对话
  # Intent: function_call  # 函数调用模式（与主 LLM 合并，无额外延迟）
```

- `nointent`：完全跳过，最快但不支持工具调用
- `function_call`：工具定义直接传给主 LLM，不额外调用意图 LLM

#### 策略 4：减少 max_tokens

限制最大输出 token 数可以减少总响应时间（但不影响 TTFT）：

```yaml
LLM:
  ChatGLMLLM:
    max_tokens: 200       # 语音场景不需要长回复
```

### 5.4 推荐配置

**追求极致低延迟（云端）：**
```
豆包/智谱 + function_call 意图模式 + max_tokens=200
```
预期端到端延迟（ASR→LLM→TTS）：**400-800ms**

**追求极致低延迟（本地）：**
```
Ollama + GPU + Qwen2.5-3B + nointent
```
预期端到端延迟：**500-1200ms**

**平衡质量与延迟：**
```
豆包/智谱（主 LLM） + function_call + FunASR 本地 GPU
```
预期端到端延迟：**600-1200ms**，且支持工具调用

---

## 六、`system_prompt.py` — 工具提示词模板

为不支持原生函数调用的提供者（Dify、Coze、FastGPT、AliBL、HomeAssistant）生成工具描述：

```python
def get_system_prompt_for_function(functions: str) -> str:
    return f"""你可以使用以下工具:
{functions}

调用工具时用JSON格式回复:
<tool_call>
{{"name": "工具名", "arguments": {{"参数": "值"}}}}
</tool_call>

如不需要调用工具，直接回复用户。回复要简洁。
"""
```

这种方式依赖 LLM 理解提示词中的工具定义，可靠性低于原生函数调用。

---

## 七、关键设计模式总结

| 设计 | 说明 |
|------|------|
| **流式优先** | 所有提供者 `yield` 逐 token 输出，TTS 可以立即开始合成 |
| **`<think>` 过滤** | 推理模型的思考过程不应朗读，全部过滤 |
| **OpenAI 兼容层** | 大量云端服务共用 `openai.py`，只需改 `base_url` |
| **函数调用双轨** | 原生支持（OpenAI/Ollama/Gemini）+ 提示词模拟（其他） |
| **Qwen3 `/no_think`** | 针对 Qwen3 模型的延迟优化，跳过思考链 |
