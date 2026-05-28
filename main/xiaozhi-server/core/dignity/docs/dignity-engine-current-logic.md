# 尊严疗法访谈引擎当前逻辑说明

本文基于 `core/dignity/engine/` 当前实现整理，用来说明尊严疗法访谈从患者输入到 AI 回复、状态推进、记忆沉淀和生命文档生成的完整逻辑。

## 1. 核心定位

当前尊严疗法访谈引擎不是普通聊天模块，而是一个“受阶段、策略、记忆和安全边界约束”的访谈状态机。

它的目标是：

1. 帮助患者回顾生命中重要的人、事、成就、角色和物件。
2. 提炼患者珍视的价值、品格、经验和力量。
3. 逐步形成患者想留给家人理解、记住或传承的话。
4. 将访谈中的有效材料沉淀为结构化记忆，并最终生成第一人称生命故事文档。

## 2. 文件职责

`graph.py`

访谈引擎主流程。负责初始化状态、构建 LangGraph、运行单轮文本输入、调用模型生成回复、应用阶段/策略元数据、记录 transcript。

`config.py`

定义访谈阶段、阶段顺序、阶段目标、默认问题、策略到路由/动作的映射、机器人动作枚举和需要规避的回复模式。

`prompts.py`

定义三类提示词：

1. 每轮回复 prompt：让模型输出阶段、策略、情绪、是否推进阶段和回复。
2. 记忆更新 prompt：从最新轮次和 transcript 中抽取结构化生命材料。
3. 生命文档 prompt：把结构化记忆整理成第一人称生命故事文稿。

`rules.py`

负责把模型输出标准化，并根据策略、阶段和轮次决定实际阶段、路由、机器人动作和眼神表情。

`replies.py`

负责清洗模型回复：限制长度、限制一次多个问题、过滤过度文学化或泛泛夸奖的表达，并在必要时回退到阶段默认问题。

`state_updates.py`

定义默认访谈记忆、默认情绪状态、情绪字段归一化和记忆合并逻辑。

`model.py`

OpenAI-compatible 模型适配层。它从配置文件读取 LLM Provider，并通过 JSON mode 调用模型。

## 3. 状态模型

核心状态类型是 `DignityState`，主要字段如下：

| 字段 | 含义 |
| --- | --- |
| `session_id` | 当前访谈会话标识 |
| `patient_text` | 患者本轮输入 |
| `current_stage` | 当前实际访谈阶段 |
| `stage_index` | 当前阶段在 `STAGE_ORDER` 中的位置 |
| `turn_count` | 总轮次 |
| `followup_count` | 当前阶段追问次数 |
| `strategy` | 本轮策略 |
| `reply` | 最终给患者的回复 |
| `emotion_state` | 患者情绪与投入度 |
| `dignity_memory` | 结构化生命故事材料 |
| `transcript` | 当前连接内的对话记录 |
| `decision_model` | 模型适配器 |

`robot_action`、`eye_expression` 等不再保存在核心状态里，而是在运行时发送事件时根据 `strategy` 临时计算。

默认记忆结构有四类：

1. `life_story_materials`：可写入生命故事的人生经历、事件、地点、物件。
2. `important_relationships`：重要关系及相关情绪。
3. `values_and_strengths`：患者体现出的价值、品格、经验或力量。
4. `messages_to_family`：想留给家人的话。

## 4. 访谈阶段

当前阶段顺序固定为：

1. `rapport`：建立关系，降低访谈压力，确认患者愿意继续交流。
2. `life_review`：人生回顾，回顾重要经历、转折和记忆线索。
3. `values`：价值提炼，表达坚持过的价值、品格和人生经验。
4. `relationships`：重要关系，梳理感谢、牵挂、和解或未尽之言。
5. `legacy_message`：留言祝福，形成留给家人、晚辈或重要他人的话。
6. `summary_confirm`：总结确认，复述重点，核对事实和下次恢复点。

阶段推进由模型判断和规则共同决定，不完全听模型输出：

1. 如果策略是 `pause`、`switch_topic` 或 `handoff_nurse`，不会推进阶段。
2. 如果模型没有要求推进，默认停留在当前阶段。
3. 如果模型检测到的阶段比当前阶段靠后，会自动推进。
4. `rapport` 阶段在至少一轮后会自动允许推进，避免一直停留在开场寒暄。

## 5. 策略

模型每轮必须输出一个 strategy。当前策略和含义如下：

| 策略 | 用途 |
| --- | --- |
| `continue_deeper` | 正常深入追问 |
| `comfort` | 承接低落、亏欠、遗憾等情绪 |
| `ask_photo_context` | 患者提到照片、物件、奖状、相册等线索 |
| `simple_followup` | 患者记不清、脑子乱时轻量追问 |
| `summarize_confirm` | 总结并核对 |
| `output_rewrite` | 医疗、诊断、财产等边界问题，转成安全回应 |
| `switch_topic` | 患者不想谈当前话题，转移话题并暂停阶段推进 |
| `pause` | 患者累了、不想说，暂停访谈 |
| `handoff_nurse` | 自伤、严重疼痛、重大医疗决策等高风险情况 |

策略在运行时会进一步映射到：

1. `robot_action`：如 `listening`、`comfort`、`pause`、`nurse_alert`。
2. `eye_expression`：如 `attentive`、`gentle`、`calm`、`concern`。

## 6. 单轮访谈执行流程

入口是 `run_text_turn(state, patient_text)`。

流程如下：

1. 如果没有旧状态，调用 `build_initial_state()` 初始化。
2. 复制旧状态，写入本轮 `patient_text`。
3. 进入 LangGraph，当前图只有两个节点：
   - `generate_reply_with_memory`
   - `record_turn`
4. `generate_reply_with_memory` 中先增加 `turn_count`。
5. 调用 `decision_model.decide_and_reply(state)`，把当前文本、记忆、transcript、阶段传给模型。
6. 模型输出 JSON，包括阶段、策略、情绪、是否推进阶段和回复。
7. `normalize_decision()` 校正非法阶段、非法策略、非 bool 的推进字段和情绪字段。
8. `apply_decision_metadata()` 根据规则落定当前阶段和下一轮追问计数。
9. `sanitize_reply()` 清洗回复。
10. 如果回复为空或被过滤，使用当前阶段的默认问题作为 fallback。
11. `record_turn()` 将本轮 patient/assistant/stage/strategy/emotion 写入 transcript。

这个设计的关键点是：模型负责“判断和生成”，规则负责“兜底和约束”。

## 7. 回复生成约束

每轮回复 prompt 明确要求：

1. 先承接患者内容或情绪，再自然推进访谈目标。
2. 不重复问已经明确的事实。
3. 一次最多问一个温和、容易回答的问题。
4. 患者累了、不想说、别问了时尊重暂停。
5. 患者要求换话题时切换话题。
6. 患者记不清或不想细问时降低粒度。
7. 不泛泛夸奖，不把患者的话升华成口号。
8. 遇到自伤、医疗决策、严重疼痛、财产等高风险内容，选择 `handoff_nurse` 或安全边界策略。
9. 回复尽量不超过 90 个中文字符。

代码层还有二次清洗：

1. 命中 `BAD_REPLY_PATTERNS` 会回退默认问题。
2. 多个问号会截断到第一个问题。
3. 超过 110 字会尝试保留第一句并追加阶段默认问题，否则直接回退默认问题。

## 8. 记忆更新逻辑

engine 内部的 `run_text_turn()` 本身只更新本轮状态和 transcript，不直接写长期记忆。

长期记忆更新在 `core/dignity/runtime.py` 的后台任务中完成：

1. 每轮 live 或 debug 访谈结束后，调用 `_schedule_background_state_update()`。
2. 后台执行 `_run_background_state_update()`。
3. 调用 `model.update_dignity_memory(next_state)`，由 LLM 根据旧记忆、最新轮次和 transcript 生成新的结构化记忆。
4. `merge_dignity_memory()` 合并旧记忆和新记忆，按稳定 JSON key 去重。
5. 每个记忆字段最多保留最后 80 条。
6. 保存到 `data/dignity_memory/{patient_id}.json`。

因此，回复生成和记忆沉淀是异步解耦的：本轮回复先返回，记忆稍后更新。

## 9. 运行时接入

前端通过 `type=dignity` 消息控制尊严疗法模式，处理器是 `core/handle/textHandler/dignityMessageHandler.py`。

支持动作：

| action | 后端处理 |
| --- | --- |
| `start` | 开启尊严访谈模式，初始化或恢复状态 |
| `stop` | 关闭模式 |
| `debug_turn` | 发送一轮调试文本 |
| `debug_reset` | 重置调试状态 |
| `generate_document` | 根据记忆生成生命文档草稿 |
| `confirm_document` | 保存患者/家属确认后的 Word 文档 |

live 语音路径中，ASR 文本会先进入普通意图处理。如果 `conn.dignity_active` 为真，`handle_dignity_turn_if_active()` 会接管本轮文本：

1. 把患者文本发给前端显示。
2. 在线程池里运行 `_run_dignity_turn()`。
3. 通过 WebSocket 发送 `dignity` 事件。
4. 如果策略是 `handoff_nurse`，额外发送 `nurse_alert`。
5. 后台更新记忆。
6. 把回复交给 TTS 播放。

## 10. 生命文档生成逻辑

当前文档生成分两步：先生成可编辑草稿，再由患者或家属核对后确认保存 Word。

流程：

1. 根据 `patient_id` 读取持久化记忆。
2. 如果当前 live/debug 状态里还有未落盘记忆，先合并进去。
3. 如果四类记忆全为空，返回 `document_error`。
4. 调用模型的 `generate_dignity_document(memory)`。
5. 模型根据生命文档 prompt 输出 Markdown。
6. 后端通过 WebSocket 返回 `document_complete`，只包含可编辑草稿：
   - `document`
   - `document_status: draft`
   - `dignity_memory`
7. 前端把草稿放进可编辑文本框，患者或家属核对事实并修改。
8. 前端发送 `confirm_document`，把确认后的 Markdown 传回后端。
9. 后端把确认后的 Markdown 转成 `.docx` 包，保存到 `data/hospice_media/dignity_documents/`。
10. 后端返回 `document_confirmed`：
   - `document`
   - `document_status: confirmed`
   - `document_url`
   - `document_filename`

当前生命文档 prompt 已改成第一人称长文模板，形式接近：

```markdown
# 某某的故事
2026年5月26日星期二

我今年……

最后，我想对我的家人说：……
```

## 11. 当前设计优点

1. 状态字段清晰，阶段、策略、动作、情绪、记忆分离。
2. 模型输出必须 JSON，便于前端和机器人动作消费。
3. 规则层对模型输出做了归一化和兜底，不完全信任模型。
4. 访谈回复与长期记忆更新解耦，降低单轮等待时间。
5. 记忆结构简单，便于生成生命故事文档。
6. `debug_turn` 使前端调试单轮访谈比较直接。

## 12. 当前风险与改进点

1. LangGraph 当前只有两个节点，状态机实际复杂度主要在函数和规则里；如果后续阶段逻辑变复杂，可以拆成更多节点。
2. `generate_reply_with_memory()` 捕获模型异常后静默 fallback，线上稳定性较好，但调试时不容易发现模型调用失败原因。
3. 记忆更新是异步后台任务，如果用户立刻点击生成文档，可能依赖当前 state_memory 合并兜底；但后台失败只打 debug 日志，前端不一定知道。
4. 文档生成依赖 LLM 对记忆的组织能力，目前没有事实核对环节；建议生成后增加“家属/患者确认并修改”的流程。
5. `.docx` 生成是轻量 OOXML 写法，足够下载和打开，但不是完整 Word 排版引擎；复杂样式、页眉页脚、目录等需要后续扩展。
6. 高风险场景目前主要由 prompt 和策略输出识别，建议未来增加关键词/规则层兜底，避免模型漏判。

## 13. 建议的后续落地顺序

1. 给 `handoff_nurse` 增加确定性的规则兜底，例如自伤、放弃治疗、严重疼痛、财产分配关键词。
2. 给生命文档增加“事实清单 + 文稿”双输出，方便家属核对。
3. 前端增加文档确认、重新生成、下载历史列表。
