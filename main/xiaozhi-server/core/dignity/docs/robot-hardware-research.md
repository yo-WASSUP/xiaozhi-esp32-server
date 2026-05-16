# 尊严疗法机器人眼睛显示模组调研

## 1. 调研目标

当前硬件目标：

- 单只眼睛显示区域约 **8-9 cm 宽**。
- 单只眼睛显示区域约 **10 cm 以上高度**，理想范围约 10-12 cm。
- 首版只需要显示静态或轻动画表情，不需要复杂 3D 眼球。
- 首版优先验证“语音服务根据对话状态控制眼睛表情”的链路。

核心判断：

- 市面上很少有正好 8-9 cm 宽、10-12 cm 高的“眼睛形状”显示模组。
- 最可落地方案是：**使用 7 英寸 HDMI LCD 竖装作为显示源，在结构上通过眼睛形状开窗/遮罩，只露出需要的眼睛区域**。
- 语音服务不应直接控制 LCD 硬件底层驱动，而应发送表情状态，由眼睛端显示程序负责渲染图片或动画。

## 2. 现有语音服务如何控制眼睛

当前 `xiaozhi-server` 已经有“情绪表情”消息通路，可作为眼睛显示控制的基础。

相关代码：

- `main/xiaozhi-server/core/connection.py`
  - LLM 流式回复开始后，会调用 `textUtils.get_emotion(self, content)`。
  - 一轮对话开头只获取一次情绪表情。
- `main/xiaozhi-server/core/utils/textUtils.py`
  - `get_emotion(conn, text)` 会从 LLM 文本中提取 emoji。
  - 然后通过 WebSocket 发送：

```json
{
  "type": "llm",
  "text": "🙂",
  "emotion": "happy",
  "session_id": "..."
}
```

安宁疗护模块里还有另一条情绪记录链路：

- `main/xiaozhi-server/core/providers/emotion/__init__.py`
  - 解析 `<!--emotion:{...}-->` 标签。
- `main/xiaozhi-server/core/connection.py`
  - 将 `emotion_mood`、`emotion_intensity` 写入会话日志。

## 3. 推荐控制链路

眼睛显示不建议走“电机/继电器式枚举控制”。它更适合走显示端状态渲染：

```text
LLM / LangGraph
  ↓
生成 display_state
  ↓
xiaozhi-server WebSocket
  ↓
眼睛显示端 WebView 页面
  ↓
切换本地图片或播放轻动画
  ↓
显示到眼睛屏幕
```

首版建议扩展现有 `type: llm` 情绪消息，不另起复杂协议：

```json
{
  "type": "eye_display",
  "session_id": "...",
  "display_state": "listening",
  "emotion": "soft",
  "asset": "eye_soft_idle",
  "duration_ms": 3000
}
```

建议的眼睛显示状态：

| 状态 | 使用场景 | 显示方式 |
| --- | --- | --- |
| `idle` | 空闲、等待唤醒 | 安静睁眼或轻微呼吸动画 |
| `listening` | 患者说话/ASR 接收 | 温和注视、轻微眨眼 |
| `thinking` | LangGraph/LLM 分析 | 慢速眨眼或目光轻微移动 |
| `speaking` | TTS 播放 | 眼神有轻微节奏变化 |
| `comfort` | 安抚节点 | 柔和眼神、低亮度暖色 |
| `happy` | 积极回忆/成就表达 | 微笑眼、亮度稍高 |
| `pause` | 暂停/结束 | 闭眼或半闭眼 |
| `nurse_alert` | 护士介入 | 严肃但温和，不闪烁 |

注意：这不是外设控制枚举表，而是显示端状态表。眼睛端可以用这些状态映射到图片或 CSS/Canvas 动画。

## 4. 7 英寸 HDMI LCD 推荐方案

推荐方案：

```text
7 英寸 HDMI LCD 竖装
  + 眼睛形状结构遮罩
  + Web 页面渲染眼睛图片/动画
  + xiaozhi-server WebSocket 控制 display_state
```

代表模组：

- Waveshare 7inch HDMI LCD (C)
- 规格参考：1024x600、显示区域 154.21 x 85.92 mm、HDMI + USB。
- 如果竖装，可得到约 **85.92 mm 宽 x 154.21 mm 高** 的显示区域。

适配情况：

- 宽度：8.59 cm，符合 8-9 cm 目标。
- 高度：15.42 cm，超过 10-12 cm 目标，可通过结构遮罩只露出 10-12 cm。
- 接口：HDMI，开发最简单。
- 控制方式：显示一个网页/全屏 App，WebSocket 收到状态后切换图片或动画。

推荐原因：

- 竖装后宽度约 8.6 cm，正好命中目标。
- 高度多出来的部分可以用结构件遮住，只露出 10-12 cm。
- HDMI 显示最容易调试。
- 不需要写屏幕底层驱动。
- 语音服务只需要通过 WebSocket 发 `display_state`。
- 可以直接接安卓盒子、树莓派、工控板或平板副屏方案。
- 可以通过网页渲染眼睛动画，资源迭代快。

风险：

- 实际屏幕高度偏高，需要结构设计遮挡。
- LCD 黑位不如 OLED，眼睛黑色区域可能不够纯。
- 单眼用一块 7 英寸屏，整机空间和功耗要确认。
- 如果最终是双眼结构，两块 7 英寸屏的宽度、供电、散热和安装空间都要重新评估。

首版结论：

- **首版只验证这一种方案。**
- 适合最快验证“大尺寸单眼 + 语音服务控制表情”的闭环。
- 不再并行调研其他尺寸屏幕，避免分散硬件验证精力。

来源：

- https://www.waveshare.com/wiki/7inch_HDMI_LCD_(C)

## 5. 眼睛显示端实现建议

### 5.1 最快实现方式

眼睛屏幕接一个能跑浏览器或 WebView 的显示主机：

- 安卓平板/安卓板。
- 树莓派。
- 工控安卓屏。
- Windows/小主机。

显示端运行一个全屏页面：

```text
eye-display.html
  - 连接 xiaozhi-server WebSocket
  - 接收 eye_display / llm emotion 消息
  - 根据 display_state 切换图片或 Canvas 动画
  - 全屏显示到眼睛屏幕
```

### 5.2 首版资源

建议先准备 8 套静态或轻动画资源：

| 状态 | 资源名 | 说明 |
| --- | --- | --- |
| `idle` | `eye_idle` | 安静睁眼 |
| `listening` | `eye_listening` | 倾听注视 |
| `thinking` | `eye_thinking` | 慢速眨眼 |
| `speaking` | `eye_speaking` | 说话状态 |
| `comfort` | `eye_comfort` | 柔和安抚 |
| `happy` | `eye_happy` | 微笑眼 |
| `pause` | `eye_pause` | 闭眼/半闭眼 |
| `nurse_alert` | `eye_nurse_alert` | 严肃温和 |

资源格式建议：

- 首版：PNG/WebP 序列或 CSS/Canvas 简单动画。
- 后续：Lottie、Rive 或 WebGL 动画。

### 5.3 服务端最小改造

首版可以不改底层 TTS/ASR，只在尊严疗法 LangGraph 输出后增加一个显示状态：

```python
display_state = {
    "continue_deeper": "listening",
    "simple_followup": "listening",
    "comfort": "comfort",
    "pause": "pause",
    "handoff_nurse": "nurse_alert",
}
```

然后通过 WebSocket 发给眼睛端：

```json
{
  "type": "eye_display",
  "display_state": "comfort",
  "asset": "eye_comfort",
  "duration_ms": 5000
}
```

现有 `type: llm` emotion 消息可以继续保留，作为普通聊天模式下的兼容通路。

## 6. 采购和验证清单

采购前需要确认：

- 实际可视区域宽高，不只看屏幕对角线。
- 是否支持 HDMI 输入。
- 是否需要额外驱动板。
- 是否可以竖屏显示。
- 是否能关闭系统边框/状态栏，实现全屏。
- 供电电压、电流和发热。
- 是否有固定孔位或 3D 结构图。
- 是否支持亮度调节。

首轮验证建议：

1. 买 1 块 7 英寸 HDMI LCD。
2. 竖屏运行一个本地眼睛网页。
3. 用黑色结构遮罩模拟 8.6 cm x 11 cm 可视窗口。
4. 从 `xiaozhi-server` 发送 `eye_display` 消息。
5. 验证 8 个状态切换是否自然。
6. 让外观负责人判断尺寸和视觉效果是否合适。

## 7. 当前结论

当前最务实的路线是：

```text
7 英寸 HDMI LCD 竖装
  + 眼睛形状遮罩
  + WebView/浏览器显示眼睛动画
  + xiaozhi-server WebSocket 控制 display_state
```

这条路线最符合首版目标：不纠结定制屏、不写底层驱动、不等硬件定制，先验证尊严疗法机器人“能看、会变表情、能被语音服务控制”的体验。

