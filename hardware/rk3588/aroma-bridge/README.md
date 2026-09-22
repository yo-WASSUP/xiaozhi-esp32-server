# RK3588 Aroma Bridge

本目录用于存放运行在 RK3588 OrangePi 上的香薰桥接服务（Aroma Bridge）代码。

本文负责说明 Aroma Bridge 程序的安装、运行和测试。RK3588 硬件参数、MQTT topic 和联调状态见 [RK3588 硬件清单](../../../docs/hardware/rk3588/README.md)。

## 第一阶段目标

- 连接本机电脑上的 Mosquitto MQTT Broker
- 订阅 `robot/rk3588-eye-001/aroma/cmd`
- 收到消息后解析 JSON
- 校验 `action_id` 属于 `aroma.start`、`aroma.stop`、`aroma.scene_relax`
- 校验并规范化 `type` 和 `duration_ms`
- 打印 `action_id`、`params`、`source_event` 和 `session_id`
- 启动后向 `robot/rk3588-eye-001/aroma/status` 发布 `online`
- 每次收到指令后向 `robot/rk3588-eye-001/aroma/status` 发布当前动作

第一阶段只跑通 MQTT 闭环，不调用真实香薰硬件，也不执行自动关闭倒计时。后续接入 GPIO、串口、继电器或厂商协议时，只扩展 Aroma Bridge 内部执行层。

## 参数规则

- `aroma.start` 默认使用 `type="1"`、`duration_ms=60000`
- `aroma.scene_relax` 固定使用 `type="1"`，允许覆盖 `duration_ms`
- `aroma.stop` 不携带参数
- `type` 只允许字符串 `"1"`、`"2"`、`"3"`
- `duration_ms` 默认 `60000`，有效范围为 `1000`～`1800000`（最长 30 分钟）
- 正整数越界时限幅到有效范围；`0`、负数和非整数会被拒绝

## 运行方式

从仓库根目录把 Aroma Bridge 同步到 RK3588：

```bash
scp -r hardware/rk3588/aroma-bridge orangepi@192.168.1.101:/home/orangepi/
```

RK3588 使用 Python `venv` 管理依赖。首次安装时先确认系统包含
`python3-venv`：

```bash
sudo apt update
sudo apt install -y python3-venv
```

进入 Aroma Bridge 目录，创建独立虚拟环境并安装依赖：

```bash
cd ~/aroma-bridge
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

启动 Aroma Bridge，当前本机电脑的局域网 IP 为 `192.168.1.100`：

```bash
source ~/aroma-bridge/.venv/bin/activate
python ~/aroma-bridge/aroma_bridge.py --broker-host 192.168.1.100
```

也可以不激活虚拟环境，直接使用其中的 Python：

```bash
~/aroma-bridge/.venv/bin/python ~/aroma-bridge/aroma_bridge.py \
  --broker-host 192.168.1.100
```

## 手动测试

在本机电脑安装并启动 Mosquitto 后，可以分别测试 Bridge 支持的三个香薰动作。

测试开启香薰 `aroma.start`：

```bash
mosquitto_pub -h 192.168.1.100 -t robot/rk3588-eye-001/aroma/cmd -m '{"type":"aroma.set","device_id":"rk3588-eye-001","session_id":"manual-test","source":"manual","source_event":"manual_test","event_time":"2026-07-22T12:00:00+08:00","action_id":"aroma.start","module":"aroma","params":{"type":"1","duration_ms":60000}}'
```

测试放松场景 `aroma.scene_relax`：

```bash
mosquitto_pub -h 192.168.1.100 -t robot/rk3588-eye-001/aroma/cmd -m '{"type":"aroma.set","device_id":"rk3588-eye-001","session_id":"manual-test","source":"manual","source_event":"manual_test","event_time":"2026-07-22T12:00:00+08:00","action_id":"aroma.scene_relax","module":"aroma","params":{"type":"1","duration_ms":60000}}'
```

测试关闭香薰 `aroma.stop`：

```bash
mosquitto_pub -h 192.168.1.100 -t robot/rk3588-eye-001/aroma/cmd -m '{"type":"aroma.set","device_id":"rk3588-eye-001","session_id":"manual-test","source":"manual","source_event":"manual_test","event_time":"2026-07-22T12:00:00+08:00","action_id":"aroma.stop","module":"aroma","params":{}}'
```

每次发布后，RK3588 终端都会打印对应的 `action_id` 和规范化参数。例如：

```text
[aroma-bridge] received_at=12:00:01 action_id=aroma.start params={"type": "1", "duration_ms": 60000} event_time=2026-07-22T12:00:00+08:00 source_event=manual_test session_id=manual-test
```

## 第一阶段边界

- 暂不调用真实香薰硬件
- 暂不操作 GPIO、串口或继电器
- 暂不执行自动关闭倒计时
- 暂不启用 MQTT 账号密码
- 暂不启用 TLS

## 后续扩展

- 增加 `aroma.*` 到真实硬件协议的映射
- 增加动作执行完成、失败和超时状态
- 增加设备侧自动关闭保护
- 增加 systemd 服务
- 公网部署时启用 MQTT 账号密码和 TLS
