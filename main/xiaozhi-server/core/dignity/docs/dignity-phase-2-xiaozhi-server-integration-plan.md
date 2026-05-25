# 尊严疗法二阶段接入 xiaozhi-server 计划

## 1. 阶段目标

第二阶段目标不是把尊严疗法混进普通自然聊天，而是在助手端界面中新增一个独立的“尊严疗法模式”。用户在界面上明确打开该模式后，ASR 文本才进入尊严疗法 LangGraph；关闭后恢复原有自然聊天流程。

本阶段打通最小闭环：

```text
助手端界面打开尊严疗法模式
  -> 设备语音输入
  -> ASR 文本
  -> dignity runtime 分流
  -> LangGraph 决策
  -> TTS 播放尊严疗法回复
  -> WebSocket 输出机器人动作枚举
```

## 2. 与自然聊天的边界

尊严疗法必须和自然聊天明确区分，原因有三点：

1. 尊严疗法是结构化访谈，不应被普通闲聊、工具调用、意图识别随意打断。
2. 尊严疗法需要记录阶段、策略、风险等级、访谈进度和下一次恢复点。
3. 尊严疗法涉及安宁疗护场景，回复边界、风险提示和人工介入策略比自然聊天更严格。

因此二阶段采用“显式模式开关”：

| 模式 | 入口 | ASR 文本去向 | 回复生成 | 外设动作 |
| --- | --- | --- | --- | --- |
| 自然聊天 | 默认模式 | 原有 `handle_user_intent` / `conn.chat` | 原有 LLM 聊天 | 原有工具/IOT |
| 尊严疗法 | 助手端界面打开 | `core.dignity.runtime` | LangGraph | 尊严疗法动作枚举 |

## 3. 助手端界面设计

### 3.1 页面入口

在助手端聊天界面中新增一个模式入口，建议用顶部模式切换或侧栏按钮：

- `自然聊天`
- `尊严疗法`

进入尊严疗法模式后，界面需要给出清晰状态，而不是只改变系统提示词。

建议状态元素：

- 当前模式：尊严疗法
- 当前访谈阶段：建立关系 / 人生回顾 / 价值提炼 / 重要关系 / 留言祝福 / 总结确认
- 当前策略：继续追问 / 安抚 / 暂停 / 转话题 / 护士介入
- 风险等级：low / medium / high
- 机器人动作：listening / comfort / pause / nurse_alert / happy
- 结束或退出模式按钮

### 3.2 UI 行为

打开尊严疗法模式：

1. 前端向服务端发送模式开启消息。
2. 服务端初始化或恢复 `conn.dignity_state`。
3. 前端显示尊严疗法状态栏。
4. 后续 ASR 文本进入 LangGraph。

关闭尊严疗法模式：

1. 前端向服务端发送模式关闭消息。
2. 服务端保留本次尊严疗法摘要状态，但停止分流。
3. 后续 ASR 文本回到自然聊天。

高风险或护士介入：

1. 服务端仍播放安全回复。
2. 前端显示醒目的人工介入提示。
3. 后续是否继续访谈由助手端人工确认。

## 4. WebSocket 消息协议

### 4.1 前端打开模式

```json
{
  "type": "dignity",
  "action": "start",
  "patient_id": "optional-patient-id",
  "session_note": "optional-note"
}
```

服务端响应：

```json
{
  "type": "dignity",
  "event": "mode_started",
  "session_id": "server-session-id",
  "data": {
    "current_stage": "rapport",
    "strategy": "continue_deeper",
    "risk_level": "low",
    "robot_action": "listening",
    "eye_expression": "soft_smile"
  }
}
```

### 4.2 前端关闭模式

```json
{
  "type": "dignity",
  "action": "stop"
}
```

服务端响应：

```json
{
  "type": "dignity",
  "event": "mode_stopped",
  "session_id": "server-session-id"
}
```

### 4.3 每轮 Graph 输出

```json
{
  "type": "dignity",
  "event": "turn_result",
  "session_id": "server-session-id",
  "data": {
    "patient_text": "我年轻时在厂里拿过先进。",
    "reply": "那段经历里，有没有一个画面或一个人让您现在还记得很清楚？",
    "current_stage": "life_review",
    "strategy": "continue_deeper",
    "risk_level": "low",
    "next_action": "ask_followup",
    "robot_action": "listening",
    "eye_expression": "attentive",
    "route": "continue"
  }
}
```

### 4.4 高风险输出

```json
{
  "type": "dignity",
  "event": "nurse_alert",
  "session_id": "server-session-id",
  "data": {
    "risk_level": "high",
    "strategy": "handoff_nurse",
    "robot_action": "nurse_alert",
    "reason": "Graph 判定需要人工介入"
  }
}
```

## 5. 后端接入方案

### 5.1 新增模块

建议新增：

```text
main/xiaozhi-server/core/dignity/
  runtime.py              # 尊严疗法模式运行时适配器
  protocol.py             # WebSocket 输入输出字段和枚举，可选
```

`runtime.py` 负责：

- 判断连接是否处于尊严疗法模式。
- 初始化 `conn.dignity_state`。
- 把 ASR 文本送入 `core.dignity.engine.graph.run_text_turn`。
- 把 Graph 输出转成 TTS 文本和 WebSocket 状态事件。
- 根据 `risk_level` 和 `strategy` 输出 `turn_result` 或 `nurse_alert`。

### 5.2 连接状态

在 `ConnectionHandler` 连接对象上新增运行时字段：

```python
conn.dignity_active = False
conn.dignity_state = None
conn.dignity_patient_id = None
```

二阶段先使用连接内存状态，不接数据库持久化。持久化、跨日恢复和 LangGraph checkpointer 放到后续阶段。

### 5.3 文本消息处理器

建议新增 `dignity` 类型文本消息处理器：

```text
core/handle/textHandler/dignityMessageHandler.py
core/handle/textMessageType.py
core/handle/textMessageHandlerRegistry.py
```

处理逻辑：

- `action=start`：开启模式，初始化 Graph state，回复 `mode_started`。
- `action=stop`：关闭模式，回复 `mode_stopped`。
- 非法 action：回复错误事件，不影响原有聊天。

### 5.4 ASR 分流点

当前语音文本进入点是：

```text
receiveAudioHandle.startToChat()
  -> handle_user_intent()
  -> conn.chat()
```

建议在 `handle_user_intent()` 中完成唤醒词、退出指令和本地动作判断之后，加入尊严疗法分流：

```python
if await handle_dignity_turn_if_active(conn, text):
    return True
```

这样可以保证：

- 退出命令仍然最高优先级。
- 唤醒词逻辑不被尊严疗法吞掉。
- 安宁疗护患者端本地动作不被 LangGraph 误处理。
- 尊严疗法开启时不会再进入普通 intent / function call / chat。

## 6. Graph 输入输出适配

### 6.1 输入

每轮输入字段：

```python
{
    "session_id": conn.session_id,
    "device_id": conn.device_id,
    "patient_id": conn.dignity_patient_id,
    "patient_text": text,
    "previous_state": conn.dignity_state,
}
```

二阶段可先复用 `core.dignity.engine.graph.run_text_turn(state, patient_text)`，后续如需拆分再迁移到更细的运行时模块。

### 6.2 输出

Graph 输出至少包含：

| 字段 | 用途 |
| --- | --- |
| `reply` | 进入 TTS 播放 |
| `current_stage` | 助手端状态展示 |
| `strategy` | 访谈策略展示和后续分支 |
| `risk_level` | 风险提示 |
| `route` | continue / pause / safety |
| `robot_action` | 外设动作枚举 |
| `eye_expression` | 眼睛表情枚举 |
| `next_action` | 下一步动作提示 |

### 6.3 TTS 播放

二阶段不新增 TTS Provider，直接复用现有 TTS 队列：

```text
Graph reply
  -> speak_txt(conn, reply)
  -> conn.tts.tts_one_sentence(...)
  -> WebSocket 音频输出
```

同时把用户输入和助手回复写入 `conn.dialogue`，便于现有日志和调试工具查看。

## 7. 外设动作枚举

二阶段只输出动作枚举，不直接驱动硬件。

建议枚举：

| `robot_action` | `eye_expression` | 含义 |
| --- | --- | --- |
| `listening` | `attentive` | 正常倾听 |
| `comfort` | `gentle` | 安抚、低落或自责场景 |
| `pause` | `calm` | 患者疲惫、拒绝或暂停 |
| `nurse_alert` | `concern` | 需要人工介入 |
| `happy` | `warm_smile` | 积极回忆、成就或照片线索 |

前端或机器人控制层收到枚举后，可以先做 UI 模拟：

- 切换眼睛表情图标。
- 显示动作日志。
- 标记后续要发给控制板的动作。

真实 USB / 蓝牙 / 控制板联动放到第三阶段。

## 8. 分阶段实施步骤

### Step 1：助手端模式入口

交付：

- UI 上出现尊严疗法模式入口。
- 可以发送 `type=dignity, action=start/stop`。
- UI 能显示当前是否处于尊严疗法模式。

验收：

- 打开后服务端返回 `mode_started`。
- 关闭后服务端返回 `mode_stopped`。
- 不打开模式时，自然聊天不受影响。

### Step 2：后端模式状态和消息处理

交付：

- 新增 dignity 文本消息 handler。
- `conn.dignity_active` 可被前端开关控制。
- 初始化 `conn.dignity_state`。

验收：

- 同一 WebSocket 连接内可打开、关闭、再次打开。
- 非法 dignity 消息不会导致连接断开。

### Step 3：ASR 文本进入 Graph

交付：

- 尊严疗法模式开启后，ASR 文本进入 LangGraph。
- 普通聊天路径被跳过。
- Graph state 保存在 `conn.dignity_state`。

验收：

- 输入“我年轻时在厂里拿过先进”，返回 `life_review`。
- 输入“我有点累了”，返回 `pause` 策略。
- 输入高风险语句，返回 `handoff_nurse` 或 `nurse_alert`。

### Step 4：TTS 播放 Graph 回复

交付：

- `reply` 进入现有 TTS 播放链路。
- 前端仍能收到原有 `stt` 和 `tts` 状态消息。

验收：

- 尊严疗法回复能被播放。
- 中断、停止、关闭连接不产生明显异常。

### Step 5：动作枚举输出

交付：

- 每轮输出 `turn_result`。
- 高风险输出 `nurse_alert`。
- UI 能显示 `stage`、`strategy`、`risk_level`、`robot_action`。

验收：

- 前端能根据 `robot_action` 做模拟动作展示。
- 日志中能看到每轮尊严疗法结构化结果。

## 9. 验收用例

| 用例 | 操作 | 期望 |
| --- | --- | --- |
| 默认自然聊天 | 不打开尊严疗法，直接说话 | 进入原有自然聊天 |
| 打开模式 | 点击尊严疗法模式 | 返回 `mode_started` |
| 人生回顾 | 说“我年轻时在厂里拿过先进” | `stage=life_review`，TTS 播放追问 |
| 疲惫暂停 | 说“我有点累了” | `strategy=pause`，`robot_action=pause` |
| 照片线索 | 说“我和老伴那张结婚照还在柜子里” | `strategy=ask_photo_context` |
| 高风险 | 说“我现在真的撑不下去了” | `risk_level=high`，输出 `nurse_alert` |
| 关闭模式 | 点击退出尊严疗法 | 返回 `mode_stopped`，后续回到自然聊天 |

## 10. 非目标

二阶段暂不做：

- LangGraph 数据库 checkpointer。
- 跨设备、跨日恢复。
- 护士端人工审核完整工作流。
- 真实控制板通信。
- 生命故事文稿自动导出。
- 完整科研数据导出。

这些放到三阶段或后续科研试用版本。

## 11. 风险与注意事项

| 风险 | 处理方式 |
| --- | --- |
| 尊严疗法误吞普通聊天 | 必须依赖 UI 显式开启，不默认启用 |
| 高风险语句处理不足 | 保持 `handoff_nurse` 优先级最高，前端显示人工介入 |
| engine state 不适合持久化 | 二阶段先内存运行，后续把 `decision_model` 移出 state |
| UI 与后端状态不一致 | 所有 start/stop 都以后端响应为准 |
| 外设协议过早复杂化 | 二阶段只发枚举，不直连硬件 |

## 12. 建议文件改动清单

后端：

```text
core/dignity/runtime.py
core/dignity/protocol.py
core/handle/textHandler/dignityMessageHandler.py
core/handle/textMessageType.py
core/handle/textMessageHandlerRegistry.py
core/handle/intentHandler.py
```

助手端界面：

```text
apps-src/patient 或实际助手端应用目录
  - 增加尊严疗法模式入口
  - 增加 dignity WebSocket 消息发送
  - 增加 dignity turn_result / nurse_alert 展示
```

如果“助手端界面”不在 `apps-src/patient`，实施前需要先确认实际前端目录，再按同一协议接入。

## 13. 完成标准

第二阶段完成时，应能演示：

1. 打开助手端尊严疗法模式。
2. 患者语音被 ASR 识别成文本。
3. 文本进入 LangGraph，而不是自然聊天。
4. LangGraph 返回尊严疗法回复。
5. 回复通过现有 TTS 播放。
6. 助手端界面显示阶段、策略、风险和机器人动作。
7. 关闭模式后恢复自然聊天。
