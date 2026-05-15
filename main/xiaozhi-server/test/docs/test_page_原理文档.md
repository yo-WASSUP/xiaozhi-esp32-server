# 小智服务器测试页面 - 客户端原理文档

## 1. 概述

`test_page.html` 是一个**浏览器端的小智语音助手客户端**，它模拟了 ESP32 硬件设备与小智服务器进行通信的完整流程。这个网页客户端实现了以下核心功能：

- **WebSocket 双向通信**：与服务器建立实时连接
- **语音录制与编码**：采集麦克风音频，使用 Opus 编码后发送
- **语音接收与播放**：接收服务器返回的 Opus 音频数据并解码播放
- **Live2D 虚拟形象**：展示动态虚拟角色，同步口型动画
- **MCP 工具调用**：支持 Model Context Protocol 工具的注册和执行
- **文字聊天**：支持文字输入方式与 AI 交互

## 6. 文件结构

```
test/
├── test_page.html              # 主页面
├── serve.py                    # Python HTTP 服务器
├── favicon.ico                 # 网站图标
├── css/
│   └── test_page.css          # 样式文件
├── js/
│   ├── app.js                 # 应用入口
│   ├── config/
│   │   ├── manager.js         # 配置管理
│   │   └── default-mcp-tools.json  # 默认 MCP 工具
│   ├── core/
│   │   ├── audio/
│   │   │   ├── opus-codec.js  # Opus 编解码
│   │   │   ├── player.js      # 音频播放
│   │   │   ├── recorder.js    # 音频录制
│   │   │   └── stream-context.js  # 流式音频上下文
│   │   ├── network/
│   │   │   ├── ota-connector.js   # OTA 连接
│   │   │   └── websocket.js       # WebSocket 处理
│   │   └── mcp/
│   │       └── tools.js       # MCP 工具管理
│   ├── ui/
│   │   ├── controller.js      # UI 控制器
│   │   └── background-load.js # 背景加载
│   ├── live2d/
│   │   ├── live2d.js          # Live2D 管理器
│   │   ├── pixi.js            # PIXI.js 渲染引擎
│   │   ├── live2dcubismcore.min.js  # Live2D 核心
│   │   └── cubism4.min.js     # Cubism 4 SDK
│   └── utils/
│       ├── libopus.js         # Opus WASM 库
│       ├── logger.js          # 日志工具
│       └── blocking-queue.js  # 阻塞队列
├── hiyori_pro_zh/             # Live2D 模型资源
└── images/                     # 背景图片
```

## 2. 整体架构

```
┌─────────────────────────────────────────────────────────────┐
│                     test_page.html                          │
│  ┌───────────────┐  ┌───────────────┐  ┌─────────────────┐  │
│  │   UI Layer    │  │  Live2D模型   │  │   聊天界面      │  │
│  │  (controller) │  │  (PIXI.js)    │  │   (弹幕式)      │  │
│  └───────┬───────┘  └───────┬───────┘  └────────┬────────┘  │
│          │                  │                   │           │
│  ┌───────┴──────────────────┴───────────────────┴────────┐  │
│  │                    App (app.js)                        │  │
│  │  - 初始化所有模块                                       │  │
│  │  - 协调各模块间的交互                                    │  │
│  └───────┬────────────────────────────────────────────────┘  │
│          │                                                   │
│  ┌───────┴────────────────────────────────────────────────┐  │
│  │                    Core Modules                         │  │
│  │  ┌─────────────┐ ┌─────────────┐ ┌───────────────────┐  │  │
│  │  │ Audio       │ │ Network     │ │ MCP Tools         │  │  │
│  │  │ - recorder  │ │ - websocket │ │ - tools.js        │  │  │
│  │  │ - player    │ │ - ota-conn  │ │                   │  │  │
│  │  │ - opus      │ │             │ │                   │  │  │
│  │  └─────────────┘ └─────────────┘ └───────────────────┘  │  │
│  └────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                              │
                              │ WebSocket (wss://)
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      小智服务器                              │
│  - OTA 认证服务 (HTTP POST /xiaozhi/ota/)                   │
│  - WebSocket 通信服务                                        │
│  - STT (语音识别)                                            │
│  - LLM (大语言模型)                                          │
│  - TTS (语音合成)                                            │
└─────────────────────────────────────────────────────────────┘
```

## 3. 核心模块详解

### 3.1 应用入口 (app.js)

**文件位置**: `js/app.js`

**职责**:
- 初始化 UI 控制器
- 加载 Opus 编解码库
- 初始化音频播放器
- 初始化 MCP 工具
- 检查麦克风可用性
- 初始化 Live2D 模型

```javascript
class App {
    async init() {
        this.uiController.init();       // 初始化 UI
        checkOpusLoaded();               // 检查 Opus 库
        initOpusEncoder();               // 初始化编码器
        this.audioPlayer = getAudioPlayer();
        await this.audioPlayer.start();  // 启动音频播放系统
        initMcpTools();                  // 初始化 MCP 工具
        await this.checkMicrophoneAvailability();
        await this.initLive2D();         // 初始化 Live2D
    }
}
```

### 3.2 网络通信模块

#### 3.2.1 OTA 连接器 (ota-connector.js)

**文件位置**: `js/core/network/ota-connector.js`

**职责**: 处理设备认证和获取 WebSocket 连接信息

**工作流程**:

1. **发送 OTA 请求**
   ```javascript
   POST {otaUrl}
   Headers:
     Content-Type: application/json
     Device-Id: {deviceId}
     Client-Id: {clientId}
   Body:
     {
       version: 0,
       application: { name: 'xiaozhi-web-test', ... },
       board: { type: deviceName, mac: deviceMac, ... },
       mac_address: deviceMac,
       ...
     }
   ```

2. **解析响应获取 WebSocket URL**
   ```javascript
   // OTA 响应结构
   {
     websocket: {
       url: "wss://xxx.xxx.xxx/websocket",
       token: "Bearer xxx"
     }
   }
   ```

3. **构建 WebSocket 连接 URL**
   - 添加 `authorization` 参数 (从 OTA 响应获取的 token)
   - 添加 `device-id` 参数
   - 添加 `client-id` 参数

#### 3.2.2 WebSocket 处理器 (websocket.js)

**文件位置**: `js/core/network/websocket.js`

**职责**: 管理 WebSocket 连接和消息处理

**消息类型**:

| 类型 | 方向 | 描述 |
|------|------|------|
| `hello` | 双向 | 握手消息，建立会话 |
| `stt` | 服务器→客户端 | 语音识别结果 |
| `llm` | 服务器→客户端 | 大模型文本回复 |
| `tts` | 服务器→客户端 | TTS 控制消息 (start/sentence_start/sentence_end/stop) |
| `listen` | 客户端→服务器 | 发送文字消息 |
| `abort` | 客户端→服务器 | 打断 AI 说话 |
| `mcp` | 双向 | MCP 工具调用 |
| `binary` | 双向 | Opus 音频数据 |

**Hello 握手流程**:
```javascript
// 客户端发送
{
  type: 'hello',
  device_id: 'xxx',
  device_name: 'xxx',
  device_mac: 'xxx',
  token: 'xxx',
  features: { mcp: true }
}

// 服务器响应
{
  type: 'hello',
  session_id: 'xxx'
}
```

**TTS 消息状态流**:
```
start → sentence_start → sentence_end → sentence_start → ... → stop
```

### 3.3 音频模块

#### 3.3.1 Opus 编解码 (opus-codec.js)

**文件位置**: `js/core/audio/opus-codec.js`

**职责**: 提供 Opus 音频编解码功能

**关键参数**:
- **采样率**: 16000 Hz
- **声道数**: 1 (单声道)
- **帧大小**: 960 samples (60ms)
- **比特率**: 16 kbps
- **复杂度**: 5

**依赖**: `js/utils/libopus.js` (WebAssembly 编译的 Opus 库)

#### 3.3.2 音频录制器 (recorder.js)

**文件位置**: `js/core/audio/recorder.js`

**职责**: 采集麦克风音频，编码为 Opus 并发送

**工作流程**:

```
┌─────────────┐     ┌──────────────┐     ┌────────────────┐     ┌──────────────┐
│ 麦克风采集   │ ──► │ PCM 16-bit   │ ──► │ Opus 编码      │ ──► │ WebSocket    │
│ (48kHz)     │     │ (重采样16kHz) │     │ (960 samples)  │     │ 发送 binary  │
└─────────────┘     └──────────────┘     └────────────────┘     └──────────────┘
```

**技术实现**:
- 使用 `AudioWorklet` 处理音频 (优先)
- 降级使用 `ScriptProcessorNode` (兼容旧浏览器)
- 每 960 个采样点（60ms）编码为一个 Opus 帧
- 录音结束时发送空帧作为停止信号

**安全限制**:
- HTTPS 或 localhost 才能使用麦克风
- HTTP 非本地访问只能使用文字交互

#### 3.3.3 音频播放器 (player.js)

**文件位置**: `js/core/audio/player.js`

**职责**: 接收 Opus 数据，解码并播放

**工作流程**:

```
┌──────────────┐     ┌──────────────┐     ┌────────────────┐     ┌──────────────┐
│ WebSocket    │ ──► │ 缓冲队列     │ ──► │ Opus 解码      │ ──► │ AudioContext │
│ 接收 binary  │     │ (BlockingQ)  │     │ (PCM 16-bit)   │     │ 播放         │
└──────────────┘     └──────────────┘     └────────────────┘     └──────────────┘
```

**关键参数**:
- **采样率**: 16000 Hz
- **缓冲策略**: 先缓冲 6 个包再开始播放
- **超时**: 400ms 超时后开始播放已有数据

### 3.4 MCP 工具模块 (tools.js)

**文件位置**: `js/core/mcp/tools.js`

**职责**: 管理和执行 MCP (Model Context Protocol) 工具

**MCP 协议消息**:

1. **工具初始化**
   ```javascript
   // 服务器请求
   { method: 'initialize', params: {...} }
   
   // 客户端响应
   {
     result: {
       protocolVersion: '2024-11-05',
       capabilities: { tools: {} },
       serverInfo: { name: 'xiaozhi-web-test', version: '2.1.0' }
     }
   }
   ```

2. **获取工具列表**
   ```javascript
   // 服务器请求
   { method: 'tools/list' }
   
   // 客户端响应
   { result: { tools: [...] } }
   ```

3. **调用工具**
   ```javascript
   // 服务器请求
   { method: 'tools/call', params: { name: 'xxx', arguments: {...} } }
   
   // 客户端响应
   { result: { content: [{ type: 'text', text: '...' }], isError: false } }
   ```

**工具定义格式**:
```javascript
{
  name: 'tool_name',
  description: '工具描述',
  inputSchema: {
    type: 'object',
    properties: {
      param1: { type: 'string', description: '参数1' }
    },
    required: ['param1']
  },
  mockResponse: { ... }  // 可选的模拟返回
}
```

### 3.5 UI 控制器 (controller.js)

**文件位置**: `js/ui/controller.js`

**职责**: 管理所有 UI 交互和状态更新

**主要功能**:
- 连接状态指示器更新
- 拨号/挂断按钮状态切换
- 录音按钮状态管理
- 聊天消息显示 (弹幕风格)
- 设置弹窗管理
- 背景切换
- MCP 工具管理界面

### 3.6 Live2D 模块

**文件位置**: `js/live2d/live2d.js`

**依赖**:
- `pixi.js` - 2D 渲染引擎
- `live2dcubismcore.min.js` - Live2D Cubism 核心
- `cubism4.min.js` - Live2D Cubism 4 SDK

**功能**:
- 加载和显示 Live2D 虚拟形象
- 同步口型动画 (基于音频分析器)
- 情绪表情动作触发
- 点击交互响应

## 4. 通信协议详解

### 4.1 连接建立流程

```
┌─────────────┐                 ┌─────────────┐                 ┌─────────────┐
│   客户端    │                 │  OTA服务器  │                 │ WebSocket   │
└──────┬──────┘                 └──────┬──────┘                 └──────┬──────┘
       │                               │                               │
       │  1. POST /xiaozhi/ota/        │                               │
       │  (设备信息)                    │                               │
       │──────────────────────────────►│                               │
       │                               │                               │
       │  2. 返回 WebSocket URL + Token│                               │
       │◄──────────────────────────────│                               │
       │                               │                               │
       │  3. WebSocket 连接 (带认证参数)                               │
       │───────────────────────────────────────────────────────────────►
       │                               │                               │
       │  4. 发送 hello 握手                                           │
       │───────────────────────────────────────────────────────────────►
       │                               │                               │
       │  5. 返回 hello + session_id                                   │
       │◄───────────────────────────────────────────────────────────────
       │                               │                               │
```

### 4.2 语音对话流程

```
┌─────────────┐                                     ┌─────────────┐
│   客户端    │                                     │   服务器    │
└──────┬──────┘                                     └──────┬──────┘
       │                                                   │
       │  1. 开始录音 → Opus 编码 → 发送二进制数据           │
       │──────────────────────────────────────────────────►│
       │  [binary: Opus frames]                            │
       │──────────────────────────────────────────────────►│
       │  ...                                              │
       │──────────────────────────────────────────────────►│
       │                                                   │
       │  2. 停止录音 → 发送空帧                            │
       │──────────────────────────────────────────────────►│
       │  [binary: empty]                                  │
       │                                                   │
       │  3. 收到语音识别结果                               │
       │◄──────────────────────────────────────────────────│
       │  { type: 'stt', text: '用户说的话' }              │
       │                                                   │
       │  4. 收到 TTS 开始                                 │
       │◄──────────────────────────────────────────────────│
       │  { type: 'tts', state: 'start' }                  │
       │                                                   │
       │  5. 收到句子开始                                   │
       │◄──────────────────────────────────────────────────│
       │  { type: 'tts', state: 'sentence_start', text }   │
       │                                                   │
       │  6. 收到 Opus 音频数据 → 解码 → 播放               │
       │◄──────────────────────────────────────────────────│
       │  [binary: Opus frames]                            │
       │                                                   │
       │  7. 收到句子结束                                   │
       │◄──────────────────────────────────────────────────│
       │  { type: 'tts', state: 'sentence_end' }           │
       │                                                   │
       │  ... (可能有更多句子)                              │
       │                                                   │
       │  8. 收到 TTS 停止                                 │
       │◄──────────────────────────────────────────────────│
       │  { type: 'tts', state: 'stop' }                   │
       │                                                   │
```

### 4.3 文字对话流程

```javascript
// 客户端发送文字消息
{
  type: 'listen',
  state: 'detect',
  text: '用户输入的文字'
}

// 如果 AI 正在说话，先发送打断消息
{
  type: 'abort',
  session_id: 'xxx',
  reason: 'wake_word_detected'
}
```

## 5. 配置管理

### 5.1 设备配置

**存储位置**: localStorage

**配置项**:
- `deviceMac` - 设备 MAC 地址 (必填)
- `clientId` - 客户端 ID
- `deviceName` - 设备名称
- `otaUrl` - OTA 服务器地址

### 5.2 MCP 工具配置

**存储位置**: localStorage (key: `mcpTools`)

**默认配置**: `js/config/default-mcp-tools.json`


## 7. 使用方法

### 7.1 启动测试服务器

```bash
cd xiaozhi-server/test
python serve.py
```

### 7.2 访问测试页面
ctrl + shift + r 强制刷新
```
http://localhost:8006/test_page.html
```

### 7.3 配置连接

1. 点击"设置"按钮
2. 填写设备 MAC 地址
3. 填写 OTA 服务器地址 (如: `http://127.0.0.1:8002/xiaozhi/ota/`)
4. 点击"拨号"按钮连接

## 8. 注意事项

1. **HTTPS 限制**: 麦克风功能需要 HTTPS 或 localhost 环境
2. **浏览器兼容性**: 建议使用 Chrome/Edge，需要支持 AudioWorklet
3. **跨域问题**: OTA 服务器需要正确配置 CORS
4. **Live2D 模型**: 需要放置正确的 Live2D 模型文件

## 9. 与 ESP32 设备的对比

| 功能 | Web 客户端 | ESP32 设备 |
|------|-----------|-----------|
| OTA 认证 | ✅ HTTP POST | ✅ HTTP POST |
| WebSocket | ✅ 浏览器原生 | ✅ ESP-IDF WebSocket |
| 音频采集 | ✅ Web Audio API | ✅ I2S 麦克风 |
| 音频播放 | ✅ Web Audio API | ✅ I2S 扬声器 |
| Opus 编解码 | ✅ libopus WASM | ✅ libopus C |
| 唤醒词检测 | ❌ 不支持 | ✅ 支持 |
| MCP 工具 | ✅ 模拟执行 | ✅ 实际执行 |
| 低功耗 | ❌ 不支持 | ✅ 支持 |

此网页客户端主要用于**调试和测试**，模拟 ESP32 设备的通信行为，便于开发者在没有硬件的情况下测试服务器功能。
