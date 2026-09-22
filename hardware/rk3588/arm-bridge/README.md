# RK3588 Arm Bridge

本目录用于存放运行在 RK3588 OrangePi 上的上肢桥接服务（Arm Bridge）代码。

本文负责说明 Arm Bridge 程序的安装、运行和测试。RK3588 硬件参数、MQTT topic 和联调状态见 [RK3588 硬件清单](../../../docs/hardware/rk3588/README.md)。

## 第一阶段目标

- 连接本机电脑上的 Mosquitto MQTT Broker
- 订阅 `robot/rk3588-eye-001/arm/cmd`
- 收到消息后解析 JSON
- 校验 `action_id` 属于 `arm.wave`、`arm.gentle`、`arm.comfort`、`arm.reset`
- 打印 `action_id`、`params`、`source_event` 和 `session_id`
- 启动后向 `robot/rk3588-eye-001/arm/status` 发布 `online`
- 每次收到指令后向 `robot/rk3588-eye-001/arm/status` 发布当前动作

第一阶段只跑通 MQTT 闭环，不调用真实硬件。后续接入 CAN、串口、厂商 SDK 或 ROS2 时，只扩展 Arm Bridge 内部执行层。

## 运行方式

从仓库根目录把 Arm Bridge 同步到 RK3588：

```bash
scp -r hardware/rk3588/arm-bridge orangepi@192.168.1.101:/home/orangepi/
```

RK3588 使用 Python `venv` 管理依赖。首次安装时先确认系统包含
`python3-venv`：

```bash
sudo apt update
sudo apt install -y python3-venv
```

进入 Arm Bridge 目录，创建独立虚拟环境并安装依赖：

```bash
cd ~/arm-bridge
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

启动 Arm Bridge，当前本机电脑的局域网 IP 为 `192.168.1.100`：

```bash
source ~/arm-bridge/.venv/bin/activate
python ~/arm-bridge/arm_bridge.py --broker-host 192.168.1.100
```

也可以不激活虚拟环境，直接使用其中的 Python：

```bash
~/arm-bridge/.venv/bin/python ~/arm-bridge/arm_bridge.py \
  --broker-host 192.168.1.100
```

## 语音触发动作

`xiaozhi-server` 会先将语音识别为文本，再按照“固定样例匹配、模糊匹配、LLM 分类兜底”的顺序选择一个 `action_id`。联调时建议使用语义明确的中文动作指令。

| action_id | 推荐语音 |
| --- | --- |
| `arm.wave` | “挥挥手”“挥手”“招招手”“打个招呼”“跟我打招呼” |
| `arm.gentle` | “轻轻动一下”“简单动一下”“摆一下手” |
| `arm.comfort` | “安慰一下”“安抚一下”“陪陪我”“我有点难过” |
| `arm.reset` | “复位”“收回来”“恢复原位”“手收回去” |

上肢方向按以下规则解析：

| 用户说法 | `side` |
| --- | --- |
| 明确说“左手”或“左臂” | `left` |
| 明确说“右手”或“右臂” | `right` |
| 没有说方向 | 使用动作默认值：`arm.wave` 为 `right`，其余 `arm.*` 为 `both` |
| 同时说到左、右 | `both` |

首次联调推荐直接说：

> 安安，挥挥手。

这句话会通过固定样例匹配识别为 `arm.wave`，无需依赖 LLM 兜底分类。不要直接念“arm wave”或“执行 arm action”，当前候选词和固定样例主要面向中文自然语言。

语音链路需要在 `main/xiaozhi-server/data/.config_hospice.yaml` 中启用机器人语音动作和上肢 MQTT 发布：

```yaml
hospice:
  enable_robot_voice_actions: true
  robot_arm:
    enabled: true
```

识别成功后，`xiaozhi-server` 日志应出现：

```text
机器人动作事件: action_id=arm.wave, module=arm, status=accepted
```

随后 Arm Bridge 应收到 `arm.wave`，默认参数为右臂、执行 `1` 次、持续 `1500` 毫秒。完整语音样例维护在 `main/xiaozhi-server/core/robot_actions/contract.py` 的 `ACTION_EXAMPLES` 中。

## 手动测试

在本机电脑安装并启动 Mosquitto 后，可以分别测试 Bridge 支持的四个动作。

测试右臂挥手 `arm.wave`：

```bash
mosquitto_pub -h 192.168.1.100 -t robot/rk3588-eye-001/arm/cmd -m '{"type":"arm.set","device_id":"rk3588-eye-001","session_id":"manual-test","source":"manual","source_event":"manual_test","event_time":"2026-07-08T12:00:00+08:00","action_id":"arm.wave","module":"arm","params":{"side":"right","repeat":1,"duration_ms":1500}}'
```

测试左臂轻柔动作 `arm.gentle`：

```bash
mosquitto_pub -h 192.168.1.100 -t robot/rk3588-eye-001/arm/cmd -m '{"type":"arm.set","device_id":"rk3588-eye-001","session_id":"manual-test","source":"manual","source_event":"manual_test","event_time":"2026-07-08T12:00:00+08:00","action_id":"arm.gentle","module":"arm","params":{"side":"left","repeat":1,"duration_ms":1000}}'
```

测试右臂安抚动作 `arm.comfort`：

```bash
mosquitto_pub -h 192.168.1.100 -t robot/rk3588-eye-001/arm/cmd -m '{"type":"arm.set","device_id":"rk3588-eye-001","session_id":"manual-test","source":"manual","source_event":"manual_test","event_time":"2026-07-08T12:00:00+08:00","action_id":"arm.comfort","module":"arm","params":{"side":"right","repeat":1,"duration_ms":2000}}'
```

测试右臂复位 `arm.reset`：

```bash
mosquitto_pub -h 192.168.1.100 -t robot/rk3588-eye-001/arm/cmd -m '{"type":"arm.set","device_id":"rk3588-eye-001","session_id":"manual-test","source":"manual","source_event":"manual_test","event_time":"2026-07-08T12:00:00+08:00","action_id":"arm.reset","module":"arm","params":{"side":"right","repeat":1,"duration_ms":1000}}'
```

每次发布后，RK3588 终端都会打印对应的 `action_id` 和规范化参数。例如：

```text
[arm-bridge] received_at=12:00:01 action_id=arm.wave params={"side": "right", "repeat": 1, "duration_ms": 1500} source_event=manual_test session_id=manual-test
```

参数范围：

- `side`：`left`、`right` 或 `both`，无效值会使用对应动作的默认方向
- `repeat`：`1`～`3`
- `duration_ms`：`500`～`3000`

## 第一阶段边界

- 暂不调用真实机械臂硬件
- 暂不生成 CAN 帧
- 暂不处理助手回复文本
- 暂不启用 MQTT 账号密码
- 暂不启用 TLS

## 后续扩展

- 增加 `arm.*` 到 CAN 帧的映射
- 增加动作执行完成、失败和超时状态
- 增加 systemd 服务
- 公网部署时启用 MQTT 账号密码和 TLS
