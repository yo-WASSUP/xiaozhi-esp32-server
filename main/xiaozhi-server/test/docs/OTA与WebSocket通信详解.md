# 🔗 OTA 与 WebSocket 通信详解


## 1. 概念解释

### 1.1 OTA 是什么？

**OTA = Over-The-Air = 空中下载/远程更新**

在本项目中，OTA 服务的作用是：
1. **设备认证**：验证客户端的身份是否合法
2. **获取连接信息**：返回 WebSocket 服务器的地址和认证 Token
3. **（可选）固件更新**：检查并推送新版本固件（ESP32 设备使用）

> 💡 你可以把 OTA 理解为一个"前台接待"，先验证你的身份，然后告诉你该去哪个会议室（WebSocket 服务器）开会。

### 1.2 WebSocket 是什么？

**WebSocket = 全双工实时通信协议**

与普通 HTTP 请求（一问一答）不同，WebSocket 建立连接后：
- 服务器可以**主动推送**消息给客户端
- 客户端也可以**随时发送**消息给服务器
- 连接保持打开状态，**延迟极低**

```
HTTP 模式（半双工）:
客户端 ──请求──► 服务器
客户端 ◄──响应── 服务器
       (每次都要重新发起请求)

WebSocket 模式（全双工）:
客户端 ◄────────► 服务器
       (连接保持，双向随时通信)
```

### 1.3 为什么需要两者配合？

| 角色 | 协议 | 作用 |
|------|------|------|
| **OTA 服务** | HTTP POST | 认证身份，获取 WebSocket 地址 |
| **WebSocket 服务** | WebSocket | 实时语音/文字通信 |

**安全考虑**：
- 不能让任何人直接连接 WebSocket 服务器
- 通过 OTA 先认证，获取临时 Token
- 使用 Token 连接 WebSocket，确保安全

---

## 2. 完整连接流程

```
┌─────────────┐         ┌─────────────┐         ┌─────────────┐
│   客户端    │         │  OTA 服务器  │         │ WebSocket   │
│ (网页/ESP32)│         │             │         │  服务器     │
└──────┬──────┘         └──────┬──────┘         └──────┬──────┘
       │                       │                       │
       │  ① POST /xiaozhi/ota/ │                       │
       │  (发送设备信息)        │                       │
       │──────────────────────►│                       │
       │                       │                       │
       │  ② 返回 WebSocket URL │                       │
       │     + Token           │                       │
       │◄──────────────────────│                       │
       │                       │                       │
       │  ③ WebSocket 连接                             │
       │     (携带 Token)                              │
       │───────────────────────────────────────────────►
       │                       │                       │
       │  ④ 发送 Hello 握手                            │
       │───────────────────────────────────────────────►
       │                       │                       │
       │  ⑤ 返回 Hello + session_id                   │
       │◄───────────────────────────────────────────────
       │                       │                       │
       │  ⑥ 开始实时通信 (语音/文字)                   │
       │◄──────────────────────────────────────────────►
       │                       │                       │
```

---

## 3. OTA 请求详解

### 3.1 请求格式

```http
POST /xiaozhi/ota/ HTTP/1.1
Host: 127.0.0.1:8002
Content-Type: application/json
Device-Id: {deviceId}
Client-Id: {clientId}
```

### 3.2 请求体 (Body)

```json
{
  "version": 0,
  "uuid": "",
  "application": {
    "name": "xiaozhi-web-test",
    "version": "1.0.0",
    "compile_time": "2025-04-16 10:00:00",
    "idf_version": "4.4.3",
    "elf_sha256": "1234567890abcdef..."
  },
  "ota": {
    "label": "xiaozhi-web-test"
  },
  "board": {
    "type": "Web测试设备",
    "ssid": "xiaozhi-web-test",
    "rssi": 0,
    "channel": 0,
    "ip": "192.168.1.1",
    "mac": "AA:BB:CC:DD:EE:FF"
  },
  "flash_size": 0,
  "minimum_free_heap_size": 0,
  "mac_address": "AA:BB:CC:DD:EE:FF",
  "chip_model_name": "",
  "chip_info": {
    "model": 0,
    "cores": 0,
    "revision": 0,
    "features": 0
  }
}
```

### 3.3 字段说明

| 字段 | 说明 | 示例值 |
|------|------|--------|
| `mac_address` | 设备唯一标识 (必填) | `AA:BB:CC:DD:EE:FF` |
| `application.name` | 应用名称 | `xiaozhi-web-test` |
| `application.version` | 应用版本 | `1.0.0` |
| `board.type` | 设备类型/名称 | `Web测试设备` |
| `board.ip` | 设备 IP 地址 | `192.168.1.1` |

> 📝 **注意**：网页客户端发送的是模拟数据，真实 ESP32 设备会发送实际的硬件信息。

### 3.4 OTA 响应

```json
{
  "websocket": {
    "url": "wss://api.xiaozhi.com/websocket",
    "token": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6..."
  },
  "firmware": {
    "version": "1.0.1",
    "url": "https://xxx/firmware.bin"
  }
}
```

| 字段 | 说明 |
|------|------|
| `websocket.url` | WebSocket 服务器地址 |
| `websocket.token` | 认证令牌 (用于连接 WebSocket) |
| `firmware` | 可选，新固件信息 (ESP32 用于 OTA 升级) |

---

## 4. WebSocket 连接详解

### 4.1 连接 URL 构建

收到 OTA 响应后，构建 WebSocket 连接 URL：

```javascript
// 原始 URL
const baseUrl = "wss://api.xiaozhi.com/websocket";

// 添加认证参数
const url = new URL(baseUrl);
url.searchParams.append('authorization', 'Bearer xxx...');
url.searchParams.append('device-id', 'device-123');
url.searchParams.append('client-id', 'web_test_client');

// 最终 URL
// wss://api.xiaozhi.com/websocket?authorization=Bearer%20xxx...&device-id=device-123&client-id=web_test_client
```

### 4.2 Hello 握手

连接成功后，立即发送 Hello 消息：

```json
{
  "type": "hello",
  "device_id": "device-123",
  "device_name": "Web测试设备",
  "device_mac": "AA:BB:CC:DD:EE:FF",
  "token": "Bearer xxx...",
  "features": {
    "mcp": true
  }
}
```

服务器响应：

```json
{
  "type": "hello",
  "session_id": "sess_abc123xyz"
}
```

> ✅ 收到 `session_id` 表示握手成功，可以开始对话！

---

## 5. WebSocket 消息类型

### 5.1 消息格式总览

| 类型 | 方向 | 数据格式 | 说明 |
|------|------|----------|------|
| `hello` | 双向 | JSON | 握手消息 |
| `stt` | 服务器→客户端 | JSON | 语音识别结果 |
| `llm` | 服务器→客户端 | JSON | AI 文字回复 |
| `tts` | 服务器→客户端 | JSON | TTS 控制消息 |
| `listen` | 客户端→服务器 | JSON | 发送文字消息 |
| `abort` | 客户端→服务器 | JSON | 打断 AI 说话 |
| `mcp` | 双向 | JSON | MCP 工具调用 |
| (二进制) | 双向 | Binary | Opus 音频数据 |

### 5.2 语音识别结果 (STT)

```json
{
  "type": "stt",
  "text": "今天天气怎么样"
}
```

### 5.3 AI 回复 (LLM)

```json
{
  "type": "llm",
  "text": "今天天气晴朗，气温25度，非常适合出门 😊",
  "emotion": "happy"
}
```

### 5.4 TTS 控制消息

TTS 采用**流式传输**，有多个状态：

```
┌─────────┐     ┌────────────────┐     ┌──────────────┐     ┌────────┐
│  start  │ ──► │ sentence_start │ ──► │ sentence_end │ ──► │  stop  │
└─────────┘     └────────────────┘     └──────────────┘     └────────┘
   开始              句子开始              句子结束            全部结束
                        │                    ▲
                        └────── 循环 ────────┘
                          (多个句子)
```

**start - 开始**
```json
{
  "type": "tts",
  "state": "start",
  "session_id": "sess_abc123"
}
```

**sentence_start - 句子开始**
```json
{
  "type": "tts",
  "state": "sentence_start",
  "text": "今天天气晴朗"
}
```

**sentence_end - 句子结束**
```json
{
  "type": "tts",
  "state": "sentence_end",
  "text": "今天天气晴朗"
}
```

**stop - 全部结束**
```json
{
  "type": "tts",
  "state": "stop"
}
```

### 5.5 发送文字消息

```json
{
  "type": "listen",
  "state": "detect",
  "text": "你好，今天天气怎么样？"
}
```

### 5.6 打断 AI 说话

当用户开始说话时，需要打断 AI 的语音输出：

```json
{
  "type": "abort",
  "session_id": "sess_abc123",
  "reason": "wake_word_detected"
}
```

### 5.7 二进制音频数据

- **客户端 → 服务器**：用户语音 (Opus 编码)
- **服务器 → 客户端**：AI 回复语音 (Opus 编码)

```javascript
// 发送音频
websocket.send(opusData);  // Uint8Array

// 接收音频
websocket.onmessage = (event) => {
  if (event.data instanceof ArrayBuffer) {
    const opusData = new Uint8Array(event.data);
    // 解码并播放...
  }
};
```

---

## 6. 完整对话流程

```
用户按下录音键
      │
      ▼
┌─────────────────────────────────────────────────────────┐
│  客户端：开始录音                                        │
│  ┌──────────────────────────────────────────────────┐   │
│  │ 麦克风 → PCM → Opus编码 → WebSocket发送(二进制)   │   │
│  └──────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
      │
      │ Opus 音频数据 (每60ms一帧)
      ▼
┌─────────────────────────────────────────────────────────┐
│  服务器：语音识别 (STT)                                  │
└─────────────────────────────────────────────────────────┘
      │
      │ { type: "stt", text: "今天天气怎么样" }
      ▼
┌─────────────────────────────────────────────────────────┐
│  服务器：大语言模型处理 (LLM)                            │
└─────────────────────────────────────────────────────────┘
      │
      │ { type: "llm", text: "今天天气晴朗..." }
      ▼
┌─────────────────────────────────────────────────────────┐
│  服务器：语音合成 (TTS)                                  │
│  ┌──────────────────────────────────────────────────┐   │
│  │ { type: "tts", state: "start" }                   │   │
│  │ { type: "tts", state: "sentence_start", text }    │   │
│  │ [二进制 Opus 数据...]                             │   │
│  │ { type: "tts", state: "sentence_end" }            │   │
│  │ { type: "tts", state: "stop" }                    │   │
│  └──────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
      │
      ▼
┌─────────────────────────────────────────────────────────┐
│  客户端：播放语音                                        │
│  ┌──────────────────────────────────────────────────┐   │
│  │ WebSocket接收 → Opus解码 → PCM → 扬声器播放       │   │
│  └──────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

---

## 7. 代码示例

### 7.1 完整连接流程 (JavaScript)

```javascript
// ① OTA 认证
async function authenticate(otaUrl, config) {
  const response = await fetch(otaUrl, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Device-Id': config.deviceId,
      'Client-Id': config.clientId
    },
    body: JSON.stringify({
      mac_address: config.deviceMac,
      application: { name: 'xiaozhi-web-test', version: '1.0.0' },
      board: { type: config.deviceName, mac: config.deviceMac }
    })
  });
  
  return await response.json();
}

// ② 建立 WebSocket 连接
function connectWebSocket(otaResult, config) {
  const url = new URL(otaResult.websocket.url);
  url.searchParams.append('authorization', otaResult.websocket.token);
  url.searchParams.append('device-id', config.deviceId);
  url.searchParams.append('client-id', config.clientId);
  
  const ws = new WebSocket(url.toString());
  ws.binaryType = 'arraybuffer';  // 接收二进制数据
  
  return ws;
}

// ③ 发送 Hello 握手
function sendHello(ws, config) {
  ws.send(JSON.stringify({
    type: 'hello',
    device_id: config.deviceId,
    device_name: config.deviceName,
    device_mac: config.deviceMac,
    features: { mcp: true }
  }));
}

// ④ 处理消息
function setupMessageHandler(ws) {
  ws.onmessage = (event) => {
    if (typeof event.data === 'string') {
      // JSON 消息
      const message = JSON.parse(event.data);
      handleJsonMessage(message);
    } else {
      // 二进制音频数据
      const audioData = new Uint8Array(event.data);
      handleAudioData(audioData);
    }
  };
}

// 完整流程
async function connect() {
  const config = {
    deviceId: 'device-123',
    clientId: 'web_test_client',
    deviceMac: 'AA:BB:CC:DD:EE:FF',
    deviceName: 'Web测试设备'
  };
  
  // 1. OTA 认证
  const otaResult = await authenticate('http://127.0.0.1:8002/xiaozhi/ota/', config);
  
  // 2. 建立 WebSocket
  const ws = connectWebSocket(otaResult, config);
  
  // 3. 连接成功后发送 Hello
  ws.onopen = () => {
    sendHello(ws, config);
    setupMessageHandler(ws);
  };
  
  return ws;
}
```

---

## 8. 常见问题

### Q: OTA 认证失败怎么办？

检查以下几点：
1. OTA 服务器地址是否正确
2. MAC 地址是否已在服务器注册
3. 网络是否能访问 OTA 服务器
4. CORS 是否配置正确（网页端）

### Q: WebSocket 连接成功但收不到 Hello 响应？

可能原因：
1. Token 过期或无效
2. device_id 与 OTA 请求不一致
3. 服务器端验证失败

### Q: 为什么用 WebSocket 而不是 HTTP？

| 特性 | HTTP | WebSocket |
|------|------|-----------|
| 连接模式 | 每次请求建立新连接 | 保持长连接 |
| 通信方向 | 客户端发起 | 双向随时 |
| 延迟 | 较高 (连接开销) | 极低 |
| 适合场景 | 网页浏览、API 调用 | 实时通信、游戏、语音 |

### Q: WebSocket 断开后如何重连？

```javascript
ws.onclose = () => {
  console.log('连接断开，3秒后重连...');
  setTimeout(() => {
    connect();  // 重新走 OTA + WebSocket 流程
  }, 3000);
};
```

---

## 9. 安全注意事项

1. **Token 有效期**：OTA 返回的 Token 通常有时效，过期需重新认证
2. **使用 HTTPS/WSS**：生产环境务必使用加密连接
3. **MAC 地址验证**：服务器应验证 MAC 地址是否已注册
4. **设备绑定**：一个 MAC 地址通常只能绑定一个用户账号

---

## 10. 总结

```
┌─────────────────────────────────────────────────────────────┐
│                       连接流程总结                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. OTA 认证 (HTTP POST)                                    │
│     └─► 验证设备身份，获取 WebSocket URL 和 Token           │
│                                                             │
│  2. WebSocket 连接 (带 Token)                               │
│     └─► 建立实时双向通信通道                                │
│                                                             │
│  3. Hello 握手                                              │
│     └─► 交换设备信息，获取会话 ID                           │
│                                                             │
│  4. 实时通信                                                │
│     ├─► 语音：Opus 二进制数据双向传输                       │
│     ├─► 文字：JSON 消息双向传输                             │
│     └─► 控制：状态消息 (TTS状态、打断等)                    │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**记住**：
- **OTA** = 身份验证 + 获取连接信息
- **WebSocket** = 实时双向通信通道
- 两者配合，实现安全、低延迟的语音交互！
