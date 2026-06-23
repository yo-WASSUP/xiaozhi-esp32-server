# 机器人动作契约表 v1

本文档定义语音/业务意图到机器人控制适配层之间的标准动作契约。

目标是让语音侧只输出稳定的 `action_id` 和参数，让硬件侧基于同一张表完成底盘、机械臂、眼睛/表情屏、香薰和通知模块的具体协议映射。

## 0. 首版语音到动作映射定位

首版目标是先让机器人真实动起来，语音到动作映射采用“硬安全规则 + 意图样例表 + LLM JSON 分类兜底”。

这一层只做四件事：

1. 停止、急停等硬安全命令先用本地规则快速命中。
2. 普通动作先用每个 `action_id` 的意图样例表匹配。
3. 样例没命中，但像机器人控制意图时，再让 LLM 做 JSON 分类。
4. 只选择一个标准 `action_id`，不让 LLM 直接调用硬件。
5. 使用默认参数，少量场景才带必要参数。

首版不走 function calling 主链路。function calling 更适合“模型选择并调用工具”，这里更需要的是“把一句话归类到固定动作表”。动作执行权必须留在控制适配层，方便做安全门禁和硬件替换。

```text
用户语音
  -> ASR 文本
  -> 硬安全规则
      - 停止、急停直接输出 action_id
  -> 意图样例表匹配
      - 包含匹配
      - 相似度匹配
      - 命中后直接输出 action_id
  -> LLM JSON 分类兜底
      - 只输出 action_id 或 no_action
      - 不调用工具
  -> 机器人控制适配层
  -> 硬件执行层
```

首版输入：

| 输入 | 说明 |
| --- | --- |
| `text` | ASR 转写文本 |

首版分类输出：

| 输出 | 说明 |
| --- | --- |
| `action_id` | 标准动作 ID |
| `params` | 可选参数，首版尽量为空 |
| `reason` | 简短原因，用于日志排查 |

LLM 分类兜底只允许输出下面这种 JSON：

```json
{
  "action_id": "base.forward",
  "reason": "用户希望机器人靠近一点"
}
```

如果不是明确机器人控制意图，必须输出：

```json
{
  "action_id": "no_action",
  "reason": "不是机器人动作控制"
}
```

示例：

```json
{
  "action_id": "arm.wave",
  "source": "voice",
  "reason": "用户表达打招呼意图",
  "params": {}
}
```

首版映射原则：

| 场景 | 处理方式 |
| --- | --- |
| 硬安全规则命中 | 直接输出 `system.stop`，不走 LLM |
| 意图样例表命中 | 直接输出一个 `action_id`，不走 LLM |
| 样例没命中但像控制指令 | 走 LLM JSON 分类兜底 |
| 只能判断情绪 | 输出一个表情动作，例如 `eye.gentle`、`eye.calm` |
| 语义含糊 | 输出 `no_action`，不乱动 |
| 涉及移动 | 只输出低速、短时默认动作 |
| 停止/别动/危险 | 直接输出 `system.stop` |

首版不把所有普通对话都送进 LLM 动作分类。只有文本里出现移动、挥手、香薰、复位、停止、机器人姿态等候选控制语义时，才启用 LLM 兜底，避免每句话都增加延迟。

意图样例表维护在 `core/robot_actions/contract.py` 的 `ACTION_EXAMPLES`。新增动作说法时优先补样例，例如：

| action_id | 样例 |
| --- | --- |
| `base.forward` | “过来一点”“靠近一点”“我看不清你”“我听不清你” |
| `arm.wave` | “挥挥手”“招招手”“打个招呼” |
| `arm.comfort` | “安慰一下”“陪陪我”“我有点难过” |
| `aroma.start` | “打开香薰”“来点香薰” |

## 1. 分工边界

```text
语音识别 / 尊严疗法引擎
  -> 输出 ASR 文本或尊严疗法动作
硬安全规则 + 意图样例表 + LLM JSON 分类兜底
  -> 输出 action_id + params
机器人控制适配层
  -> 动作校验、状态检查、安全门禁、协议路由
硬件执行层
  -> ROS2 / MQTT / TCP / 串口 / CAN / Home Assistant 等真实控制
```

| 角色 | 负责内容 | 不负责内容 |
| --- | --- | --- |
| 语音/业务侧 | 识别用户原始表达、维护对话上下文和尊严疗法策略 | 不直接拼硬件协议、不直接控制电机 |
| 动作分类层 | 从一句 ASR 文本或业务动作中选择标准动作 | 不做复杂多轮推理、不下发真实硬件协议 |
| 控制适配层 | 校验动作、补默认参数、处理安全门禁、选择协议通道 | 不决定业务语义 |
| 硬件侧 | 将 `action_id` 映射到真实硬件指令并回传状态 | 不解析自然语言 |

## 2. 动作请求格式

语音侧输出给控制适配层的最小结构如下：

```json
{
  "action_id": "arm.wave",
  "source": "voice",
  "reason": "用户说：跟我打个招呼",
  "params": {}
}
```

字段说明：

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `action_id` | 是 | 标准动作 ID，硬件侧按此字段映射 |
| `source` | 是 | 来源，建议值：`voice`、`dignity_engine`、`system`、`manual` |
| `reason` | 否 | 触发原因，便于调试和日志追踪 |
| `params` | 否 | 动作参数，首版默认 `{}`，只有方向、香薰档位等必要场景才传 |

首版语音侧尽量只传 `action_id`。参数由控制适配层或硬件侧按默认值补齐，减少语义判断耗时。

## 3. 动作命名规则

`action_id` 使用 `模块.动作` 格式：

| 模块 | 说明 |
| --- | --- |
| `system` | 系统级动作，例如停止、空闲、恢复 |
| `base` | 底盘动作 |
| `arm` | 四肢/机械臂动作 |
| `eye` | 眼睛/表情屏动作 |
| `aroma` | 香薰动作 |
| `notify` | 护士提醒、外部通知等 |

# 标准动作表

## 1. 系统动作

| action_id       | 中文名    | 触发意图     |
| --------------- | ------ | -------- |
| `system.idle`   | 空闲待机   | 对话结束、无动作 |
| `system.stop`   | 停止当前动作 | 停止、别动、暂停 |
| `system.resume` | 恢复默认状态 | 继续、恢复    |

---

## 2. 底盘动作

| action_id         | 中文名  | 触发意图      |
| ----------------- | ---- | --------- |
| `base.forward`    | 前进   | 过来一点、往前走  |
| `base.backward`   | 后退   | 后退一点、离远一点 |
| `base.turn_left`  | 左转   | 向左转、看左边   |
| `base.turn_right` | 右转   | 向右转、看右边   |
| `base.move`       | 特定动作 | 暂定        |

### 底盘参数约束

| 参数            | 类型        | 范围           | 说明             |
| ------------- | --------- | ------------ | -------------- |
| `speed`       | `number`  | `0.1 - 0.5`  | 首版建议低速，适配层可再限速 |
| `duration_ms` | `integer` | `200 - 3000` | 单次移动持续时间       |
| `angle`       | `integer` | `5 - 90`     | 单次转向角度         |

---

## 3. 上肢／机械臂动作

| action_id     | 中文名  | 触发意图      |
| ------------- | ---- | --------- |
| `arm.wave`    | 挥手   | 打招呼、挥挥手   |
| `arm.gentle`  | 轻微摆动 | 简单动作      |
| `arm.comfort` | 安抚动作 | 安慰、陪伴、别难过 |
| `arm.reset`   | 复位   | 收回来、恢复原位  |

### 机械臂参数约束

| 参数            | 类型        | 可选值／范围         | 说明     |
| ------------- | --------- | -------------- | ------ |
| `side`        | `string`  | `left`、`right` | 使用哪侧手臂 |
| `repeat`      | `integer` | `1 - 3`        | 重复次数   |
| `duration_ms` | `integer` | `500 - 3000`   | 动作持续时间 |

---

## 4. 眼睛／表情屏动作

| action_id        | 中文名  | 触发意图       | 硬件侧责任  |
| ---------------- | ---- | ---------- | ------ |
| `eye.calm`       | 平静   | 空闲、暂停、恢复平静 | 切换平静表情 |
| `eye.warm_smile` | 微笑   | 开心、感谢、积极反馈 | 切换微笑表情 |
| `eye.attentive`  | 专注倾听 | 倾听、继续追问    | 切换专注表情 |
| `eye.speak`      | 说话   | 机器人说话时     | 切换说话表情 |
| `eye.gentle`     | 温和安抚 | 悲伤、低落、安慰   | 切换温和表情 |
| `eye.concern`    | 关切   | 风险、护士介入    | 切换关切表情 |

---

## 5. 香薰动作

| action_id           | 中文名  | 触发意图      | 硬件侧责任    |
| ------------------- | ---- | --------- | -------- |
| `aroma.start`       | 开启香薰 | 打开香薰、放松一下 | 按档位和时长开启 |
| `aroma.stop`        | 关闭香薰 | 关掉香薰、不要香味 | 关闭香薰     |
| `aroma.scene_relax` | 放松场景 | 安抚、睡前、紧张  | 使用放松场景参数 |

### 香薰参数约束

| 参数            | 类型        | 范围               | 说明   |
| ------------- | --------- | ---------------- | ---- |
| `level`       | `integer` | `1 - 3`          | 香薰档位 |
| `type`        | `string`  | 暂定               | 香薰种类 |
| `duration_ms` | `integer` | `60000 - 600000` | 开启时长 |

---

## 6. 通知动作

| action_id            | 中文名  | 触发意图        | 硬件侧责任       |
| -------------------- | ---- | ----------- | ----------- |
| `notify.nurse_alert` | 护士提醒 | 明显风险、需要人工介入 | 推送护士提醒或本地告警 |

### 通知参数约束

| 参数      | 类型       | 可选值               | 说明   |
| ------- | -------- | ----------------- | ---- |
| `level` | `string` | `normal`、`urgent` | 提醒等级 |


## 5. 尊严疗法动作映射

当前尊严疗法引擎已有 `robot_action` 和 `eye_expression` 抽象字段。建议首版按下表映射到标准动作：

| robot_action | 语义 | 标准动作组合 |
| --- | --- | --- |
| `idle` | 空闲 | `system.idle` + `eye.calm` |
| `listening` | 倾听 | `eye.attentive` |
| `comfort` | 安抚 | `eye.gentle` + 可选 `arm.comfort` + 可选 `aroma.scene_relax` |
| `pause` | 暂停 | `system.stop` + `eye.calm` |
| `nurse_alert` | 护士介入 | `system.stop` + `eye.concern` + `notify.nurse_alert` |
| `happy` | 积极反馈 | `eye.warm_smile` + 可选 `arm.wave` |

`eye_expression` 可继续作为表情层的快捷字段，但硬件侧最终以 `eye.*` 动作为准。

## 6. 语音到动作映射建议

| 用户说法示例 | 输出 action_id | 首版参数 |
| --- | --- | --- |
| “停一下”“别动”“先暂停” | `system.stop` | `{}` |
| “过来一点”“往前一点” | `base.forward` | `{}` |
| “离远一点”“后退一点” | `base.backward` | `{}` |
| “向左转一下” | `base.turn_left` | `{}` |
| “向右转一下” | `base.turn_right` | `{}` |
| “挥挥手”“打个招呼” | `arm.wave` | `{}` |
| “收回来” | `arm.reset` | `{}` |
| “打开香薰” | `aroma.start` | `{}` |
| “关掉香薰” | `aroma.stop` | `{}` |

首版语音侧只负责选动作。速度、角度、持续时间、挥手次数、香薰时长都先由控制适配层使用默认值。

## 7. 安全门禁约定

适配层收到动作后，必须先做安全检查：

| 检查项 | 适用动作 | 处理方式 |
| --- | --- | --- |
| 急停状态 | 全部动作 | 只允许 `system.stop`、`notify.nurse_alert`、`eye.*` |
| 障碍物距离 | `base.*` | 距离不足时拒绝移动 |
| 电量过低 | `base.*`、`arm.*`、`aroma.*` | 拒绝非必要动作，允许 `system.stop` |
| 硬件故障 | 对应模块 | 拒绝该模块动作并回传错误 |
| 动作超时 | 全部动作 | 由适配层内部设置超时 |
| 参数越界 | 全部动作 | 适配层限幅或拒绝 |

## 8. 控制适配层首版实现

首版控制适配层先做成服务端内部模块，不直接依赖具体 ROS2、MQTT、串口或 CAN。

建议代码结构：

```text
core/robot_actions/
  contract.py     # 标准动作 ID、默认参数、动作分组、意图样例表
  classifier.py   # 硬安全规则 + 样例匹配 + LLM JSON 分类兜底
  adapter.py      # 校验、补默认参数、安全门禁、事件下发
```

首版执行链路：

```text
ASR 文本
  -> classifier.classify_robot_action()
  -> adapter.dispatch_robot_action()
  -> websocket client_action 事件
  -> 前端 / 硬件桥 / 后续真实驱动
```

首版下发事件：

```json
{
  "type": "client_action",
  "action": "robot_action",
  "source": "voice",
  "action_id": "arm.wave",
  "params": {},
  "status": "accepted",
  "reason": "用户表达打招呼意图"
}
```

后续接真实硬件时，只需要在 `adapter.py` 内部把不同模块路由到真实 driver：

| action_id 前缀 | driver |
| --- | --- |
| `eye.*` | 表情屏 driver |
| `base.*` | 底盘 driver |
| `arm.*` | 上肢/机械臂 driver |
| `aroma.*` | 香薰 driver |
| `notify.*` | 通知 driver |

眼睛表情不只由语音触发，也可以由系统状态触发：

| 系统状态 | 建议动作 |
| --- | --- |
| 空闲 | `eye.calm` |
| 用户说话 / 正在听 | `eye.attentive` |
| 机器人说话 | `eye.speak` |
| 安抚 | `eye.gentle` |
| 风险提醒 | `eye.concern` |

## 9. 适配层返回格式

建议硬件适配层返回统一结果：

```json
{
  "action_id": "arm.wave",
  "status": "accepted",
  "message": "动作已接收",
  "hardware_task_id": "task_20260615_001",
  "rejected_reason": ""
}
```

`status` 建议值：

| status | 说明 |
| --- | --- |
| `accepted` | 已接收并开始执行 |
| `completed` | 执行完成 |
| `rejected` | 因安全、状态或参数问题拒绝 |
| `failed` | 已下发但硬件执行失败 |
| `timeout` | 动作超时 |

## 10. 首版落地顺序

建议先实现最小闭环：

1. `system.stop`
2. `eye.calm`
3. `eye.attentive`
4. `eye.gentle`
5. `eye.concern`
6. `arm.wave`
7. `arm.reset`
8. `aroma.start`
9. `aroma.stop`
10. `base.forward`
11. `base.backward`
12. `base.turn_left`
13. `base.turn_right`

底盘动作风险更高，应在急停、避障、限速确认后再进入真实设备联调。
