# 尊严疗法机器人技术路线方案

## 1. 项目定位

本项目面向安宁疗护场景下的主动式心理支持需求，目标是构建一个具备主动访谈能力、清晰治疗逻辑、可控决策机制和机器人陪伴反馈的尊严疗法机器人原型。

## 2. 首版目标

首版目标是快速打通尊严疗法机器人最小可用闭环：

1. 患者可以通过语音与机器人进行尊严疗法访谈。
2. AI 能主动推进人生回顾、重要关系、人生价值、遗愿祝福等主题。
3. 系统能记录访谈进度、关键事件、人物关系、情绪状态和下次恢复点。
4. AI 能根据患者状态选择继续追问、换话题、安抚、暂停或建议护士介入。
5. 机器人可通过眼睛表情、耳朵/手部动作、香薰等外设形成基础陪伴感。
6. 系统能输出结构化访谈摘要和生命故事文稿。

后续可加入功能：

- 高复杂度强化学习自动生成节点库。
- 高精度情绪识别模型。
- 全自动视频成片。

## 3. 总体架构

系统采用“实时交互前端 + LangGraph 决策编排层 + 机器人控制层”的分层架构。

```text
患者语音
  ↓
ASR 流式识别
  ↓
实时交互前端
  - 快速响应
  - 语气词/确认语
  - 中断处理
  - TTS 播放
  ↓
LangGraph 决策编排层
  - 访谈阶段判断
  - 情绪/风险判断
  - 节点策略选择
  - LLM 回复生成
  - 记忆卡片更新
  - 护士介入中断
  ↓
机器人控制层
  - 眼睛表情
  - 耳朵动作
  - 手部动作
  - 香薰开关
  - 底盘控制
```

设计原则：

- 前端负责低延迟交互，LangGraph 负责状态、节点、分支和恢复。
- 能并行的环节尽量并行，降低用户等待感。
- 决策逻辑优先可控、可编辑、可复盘。
- 首版保持架构简单。

## 4. LangGraph 接入方案

### 4.1 为什么引入 LangGraph

尊严疗法机器人不是一次性问答，而是一个长周期、可中断、可恢复、可人工介入的状态流程。LangGraph 适合承担主流程编排，因为它本身面向 long-running、stateful agent 工作流，官方能力包括持久化、durable execution、streaming、human-in-the-loop 和 memory。

对本项目的价值：

- 用 graph 表达尊严疗法阶段和节点跳转。
- 用 state 保存当前阶段、风险、情绪、记忆卡片和外设状态。
- 用 checkpoint 支持跨日恢复访谈。
- 用 interrupt 支持护士/研究人员介入审核。
- 用 streaming 同时支持语音生成和节点状态回传。
- 用 tool/action 节点统一管理机器人外设调用。

### 4.2 推荐接入方式

首版建议以 Python 侧新增独立模块接入：

```text
main/xiaozhi-server/
  core/
    dignity/
      graph.py              # LangGraph 主图
      state.py              # DignityState 定义
      nodes/
        input_safety.py
        stage_router.py
        strategy_router.py
        response_generator.py
        output_safety.py
        memory_writer.py
        robot_action.py
        nurse_interrupt.py
      templates/
        question_bank.yaml
        node_strategy.yaml
        output_rules.yaml
        robot_actions.yaml
```

现有 `xiaozhi-server` 保持 ASR、TTS、WebSocket、设备连接等能力；LangGraph 只接管“尊严疗法模式”下的对话决策。

### 4.3 Graph State 设计

建议定义 `DignityState`，每轮对话都读写这个状态：

```python
class DignityState(TypedDict):
    session_id: str
    device_id: str
    patient_id: str
    turn_id: int
    user_text: str
    current_stage: str
    current_node: str
    emotion: str
    risk_level: str
    strategy: str
    covered_topics: list[str]
    memory_cards: list[dict]
    photo_requests: list[dict]
    nurse_alert: dict | None
    robot_action: dict
    ai_reply: str
    next_resume_point: str
```

关键字段说明：

| 字段 | 用途 |
| --- | --- |
| `current_stage` | 当前尊严疗法阶段，如建立关系、人生回顾、价值提炼 |
| `current_node` | 当前节点，如继续追问、安抚、暂停、护士介入 |
| `emotion` | 当前情绪判断，如平稳、低落、疲惫、抗拒 |
| `risk_level` | 风险等级：low、medium、high |
| `strategy` | 本轮策略：continue_deeper、switch_topic、comfort、pause、handoff_nurse |
| `memory_cards` | 结构化人生事件、人物关系、价值观和恢复点 |
| `robot_action` | 本轮要发送给眼睛、耳朵、手部、香薰的动作枚举 |

### 4.4 节点设计

首版 Graph 节点建议如下：

```text
START
  ↓
input_safety_node
  ↓
stage_router_node
  ↓
strategy_router_node
  ├─ high risk → nurse_interrupt_node
  ├─ pause → pause_response_node
  └─ normal → response_generator_node
       ↓
output_safety_node
       ↓
robot_action_node
       ↓
memory_writer_node
       ↓
END
```

节点职责：

| 节点 | 职责 |
| --- | --- |
| `input_safety_node` | 检查患者输入是否有高风险、自伤、强痛苦、拒绝继续等信号 |
| `stage_router_node` | 根据访谈进度选择当前阶段 |
| `strategy_router_node` | 根据患者状态选择追问、换话题、安抚、暂停或护士介入 |
| `response_generator_node` | 调用 LLM 生成自然语言回复 |
| `output_safety_node` | 检查 AI 回复是否越界、诊断、过度追问或空洞安慰 |
| `robot_action_node` | 把对话策略映射成眼睛、耳朵、手、香薰枚举 |
| `memory_writer_node` | 写入记忆卡片、摘要、下次恢复点 |
| `nurse_interrupt_node` | 高风险时暂停自动推进，等待护士/研究人员处理 |


### 4.5 持久化与恢复

LangGraph 需要启用 checkpointer，并用 `session_id` 或 `patient_id + session_id` 作为 `thread_id`。

```text
thread_id = dignity:{patient_id}:{session_id}
```

恢复逻辑：

1. 患者重新进入尊严疗法模式。
2. 根据 `thread_id` 读取上次 Graph state。
3. 从 `next_resume_point` 生成温和恢复语。
4. 继续进入 `stage_router_node`。

### 4.6 人工介入

当 `risk_level = high` 或策略为 `handoff_nurse` 时，Graph 进入 interrupt：

```text
nurse_interrupt_node
  - 暂停自动追问
  - 输出风险原因
  - 输出最近 3 轮对话摘要
  - 等待护士选择：
    1. 继续但换安全话题
    2. 暂停访谈
    3. 人工接管
```


### 4.7 接入阶段

| 阶段 | 接入目标 | 范围 |
| --- | --- | --- |
| 概念验证 | 验证 LangGraph 能否跑通尊严疗法状态机 | 本地脚本，输入文本，输出策略和回复 |
| V1 | 接入 `xiaozhi-server` 尊严疗法模式 | ASR 文本进入 Graph，Graph 输出回复和动作枚举 |
| V2 | 接入持久化和护士介入 | 使用数据库 checkpointer，支持恢复和 interrupt |
| V3 | 接入科研复盘与评估 | 导出节点轨迹、策略判断、风险事件、效果评价 |

## 5. AI 尊严疗法对话路线

### 5.1 访谈阶段

| 阶段 | 目标 | 示例话题 |
| --- | --- | --- |
| 建立关系 | 降低紧张感，说明访谈目的 | 今天想轻松聊聊您生命中重要的事情 |
| 人生回顾 | 收集关键人生经历 | 童年、工作、家庭、转折点 |
| 价值提炼 | 帮患者表达力量、价值观和自我认同 | 最骄傲的事、困难中如何坚持 |
| 重要关系 | 梳理想感谢、想道歉、想祝福的人 | 家人、朋友、同事、照护者 |
| 留言祝福 | 形成可交付给家属的文字素材 | 想留给家人的话、嘱托、祝福 |
| 总结确认 | 复述重点，确认是否准确 | 让患者确认故事是否符合本意 |

每轮对话都应关联当前阶段和阶段目标，避免变成开放式闲聊。

### 5.2 节点决策机制

首版采用“节点 + 策略”的对话控制方式，而不是完全依赖 LLM 自由发挥。

核心策略：

- `continue_deeper`：患者情绪稳定且内容积极，继续深入追问。
- `switch_topic`：当前话题可能带来负面情绪，切换到更安全主题。
- `comfort`：患者低落、自责、悲伤时先安抚。
- `pause`：患者疲惫、沉默、拒绝继续时暂停。
- `ask_photo_context`：当前故事适合提醒家属补充照片。
- `handoff_nurse`：出现明显心理风险或强烈痛苦时建议护士介入。


## 6. 机器人整机功能路线

### 6.1 外设功能

| 模块 | 首版能力 | 控制方式 |
| --- | --- | --- |
| 眼睛 | 显示静态情绪表情 | 枚举值切换图片 |
| 耳朵 | 简单摆动 | 枚举值控制电机动作 |
| 手部 | 抬起、放下、摆动 | 枚举值控制电机动作 |
| 香薰 | 语音触发开关，支持时长控制 | IO 控制继电器 |
| 底盘 | 调用底盘 API 进行移动/导航 | 网络 API |

### 6.2 平板与控制板通信

优先验证路径：

1. 安卓平板通过 USB 与控制板通信。
2. 安卓平板通过蓝牙与控制板通信。
3. 若消费级平板受限，评估工业安卓平板串口通信。
4. 若仍不可行，再评估额外控制网关或工控机。

首版目标是打通：

```text
安卓平板 App
  ↓ USB/蓝牙/串口
控制板
  ↓
电机 / 继电器 / 表情屏
```

## 7. 软件模块拆解

| 模块 | 职责 | 优先级 |
| --- | --- | --- |
| LangGraph 主流程 | 管理访谈阶段、节点、策略转移、人工中断 | P0 |
| 结构化决策与状态约束 | 输出阶段、策略、风险等级和动作字段 | P0 |
| 记忆卡片 | 提取事件、人物、价值观、恢复点 | P0 |
| 主动提问模板库 | 每阶段可编辑问题和追问模板 | P0 |
| 机器人动作协议 | 定义眼耳手香薰枚举指令 | P0 |
| 平板通信验证 Demo | USB/蓝牙发送枚举指令到控制板 | P0 |
| 生命故事草稿生成 | 根据记忆卡片生成文稿初稿 | P1 |
| 家属照片线索 | 记录需要家属补充的照片/事件 | P1 |
| 眼睛表情资源 | 静态表情图片和切换逻辑 | P1 |
| 底盘 API 封装 | 网络 API 控制底盘 | P2 |
| 视频脚本生成 | 由文稿和照片生成视频脚本 | P2 |

## 8. 分阶段实施计划

### 阶段一：LangGraph 文本 概念验证

目标：验证尊严疗法主动对话状态机。 本地命令行 Demo：输入患者文本，输出阶段、策略、回复和动作枚举。

验收：

- AI 能主动推进 3 个以上尊严疗法主题。
- 患者中断后可恢复上次上下文。
- 出现低落或拒绝时能转向安抚或暂停。
- 输出内容不包含临床诊断或不当安慰。

### 阶段二：接入 `xiaozhi-server`

目标：让 ASR 文本进入 LangGraph，LangGraph 输出回复和机器人动作。

交付：

- 尊严疗法模式入口。
- Graph 输入/输出适配器。
- TTS 播放回复。
- 外设动作枚举输出。

### 阶段三：机器人外设通信验证

目标：验证安卓平板到控制板再到外设的物理链路。

交付：

- USB 通信 Demo。
- 蓝牙通信 Demo。
- 枚举动作协议。
- 控制板接收并驱动电机/继电器 Demo。
- 香薰开关与时长控制 Demo。

### 阶段四：华西科研试用版本

目标：形成可在华西小范围科研试用的版本。

交付：

- 访谈流程配置。
- 访谈日志导出。
- 生命故事草稿导出。
- 外设基本联动。
- 风险提示与人工确认机制。

## 9. 四个基础文档初稿

### 9.1 尊严疗法访谈问题库 v1

### 9.2 尊严疗法节点策略表 v1

### 9.3 机器人外设与眼睛模组调研表 v1

### 9.4 尊严疗法机器人验收用例 v1

## 11. 关键风险与验证

| 风险 | 影响 | 验证方式 | 负责人 |
| --- | --- | --- | --- |
| 安卓平板无法稳定控制外设 | 机器人动作链路受阻 | USB/蓝牙 Demo | 唐辉煌 |
| 大尺寸眼睛模组成本或安装不可接受 | 外观方案受影响 | 硬件调研与采购测试 | 唐辉煌/孙萌 |
| LangGraph 引入后复杂度上升 | 首版进度受影响 | 先做文本 概念验证，再接入主服务 | 唐辉煌 |
| LLM 输出不可控 | 不适合医疗科研场景 | 节点策略 + 输出控制 + 用例测试 | 唐辉煌 |
| function calling 导致延迟高 | 交互体验下降 | 对比规则/分类器/结构化输出方案 | 唐辉煌 |
| 尊严疗法问题过于机械 | 患者体验差 | 问题库与真实访谈反馈迭代 | 孙萌 |
| 情绪风险识别不足 | 安全风险 | 风险词、护士介入节点、人工复核 | 唐辉煌 |

## 12. 参考资料

- LangGraph 官方概览：https://docs.langchain.com/oss/python/langgraph/overview
- LangGraph durable execution：https://docs.langchain.com/oss/python/langgraph/durable-execution
- LangGraph interrupts / human-in-the-loop：https://docs.langchain.com/oss/python/langgraph/interrupts
- NeMo Guardrails GitHub：https://github.com/NVIDIA-NeMo/Guardrails

## 13. 总结

尊严疗法机器人首版的核心不是“做一个会聊天的机器人”，而是做一个能主动推进尊严疗法访谈、能被研究人员控制和复盘、能通过基础外设形成陪伴感的科研原型。

技术路线建议：

- 用 LangGraph 做主流程编排和状态机。
- 做输入/输出安全控制。
- 用节点策略表保证尊严疗法对话可控。
- 用外设动作枚举把 AI 状态映射到机器人反馈。
- 先做文本 概念验证 和物理通信验证，再接入完整机器人。
