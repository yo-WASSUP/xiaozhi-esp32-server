# RK3588 Eye Bridge

本目录用于存放运行在 RK3588 OrangePi 上的眼睛桥接服务（Eye Bridge）代码。

本文负责说明 Eye Bridge 程序的安装、运行和测试。RK3588 硬件参数、MQTT topic 和联调状态见 [RK3588 硬件清单](../../../docs/hardware/rk3588/README.md)。

## 第一阶段目标

- 连接本机电脑上的 Mosquitto MQTT Broker
- 订阅 `robot/rk3588-eye-001/eye/cmd`
- 收到消息后解析 JSON
- 打印 `action_id`
- 启动后向 `robot/rk3588-eye-001/eye/status` 发布 `online`
- 每次收到指令后向 `robot/rk3588-eye-001/eye/status` 发布当前 `action_id`
- 重复 `action_id` 不再推送给 Eye Renderer，减少无意义屏幕刷新

## 运行方式

从仓库根目录把 Eye Bridge 同步到 RK3588：

```bash
scp -r hardware/rk3588/eye-bridge orangepi@192.168.1.101:/home/orangepi/
```

RK3588 使用 Python `venv` 管理依赖。首次安装时先确认系统包含
`python3-venv`：

```bash
sudo apt update
sudo apt install -y python3-venv
```

进入 Eye Bridge 目录，创建虚拟环境并安装依赖：

```bash
cd ~/eye-bridge
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

启动 Eye Bridge，当前本机电脑的局域网 IP 为 `192.168.1.100`：

```bash
source ~/eye-bridge/.venv/bin/activate
python ~/eye-bridge/eye_bridge.py --broker-host 192.168.1.100
```

也可以不激活虚拟环境，直接使用其中的 Python：

```bash
~/eye-bridge/.venv/bin/python ~/eye-bridge/eye_bridge.py \
  --broker-host 192.168.1.100
```

## 手动测试

在本机电脑安装并启动 Mosquitto 后，可以分别测试 Bridge 支持的六个眼睛动作。

测试平静表情 `eye.calm`：

```bash
mosquitto_pub -h 192.168.1.100 -t robot/rk3588-eye-001/eye/cmd -m '{"type":"eye.set","device_id":"rk3588-eye-001","session_id":"manual-test","source":"manual","source_event":"manual_test","event_time":"2026-06-23T15:59:32+08:00","action_id":"eye.calm"}'
```

测试温暖微笑 `eye.warm_smile`：

```bash
mosquitto_pub -h 192.168.1.100 -t robot/rk3588-eye-001/eye/cmd -m '{"type":"eye.set","device_id":"rk3588-eye-001","session_id":"manual-test","source":"manual","source_event":"manual_test","event_time":"2026-06-23T15:59:32+08:00","action_id":"eye.warm_smile"}'
```

测试专注倾听 `eye.attentive`：

```bash
mosquitto_pub -h 192.168.1.100 -t robot/rk3588-eye-001/eye/cmd -m '{"type":"eye.set","device_id":"rk3588-eye-001","session_id":"manual-test","source":"manual","source_event":"manual_test","event_time":"2026-06-23T15:59:32+08:00","action_id":"eye.attentive"}'
```

测试说话表情 `eye.speak`：

```bash
mosquitto_pub -h 192.168.1.100 -t robot/rk3588-eye-001/eye/cmd -m '{"type":"eye.set","device_id":"rk3588-eye-001","session_id":"manual-test","source":"manual","source_event":"manual_test","event_time":"2026-06-23T15:59:32+08:00","action_id":"eye.speak"}'
```

测试温和安抚 `eye.gentle`：

```bash
mosquitto_pub -h 192.168.1.100 -t robot/rk3588-eye-001/eye/cmd -m '{"type":"eye.set","device_id":"rk3588-eye-001","session_id":"manual-test","source":"manual","source_event":"manual_test","event_time":"2026-06-23T15:59:32+08:00","action_id":"eye.gentle"}'
```

测试关切表情 `eye.concern`：

```bash
mosquitto_pub -h 192.168.1.100 -t robot/rk3588-eye-001/eye/cmd -m '{"type":"eye.set","device_id":"rk3588-eye-001","session_id":"manual-test","source":"manual","source_event":"manual_test","event_time":"2026-06-23T15:59:32+08:00","action_id":"eye.concern"}'
```

每次发布后，RK3588 终端都会打印对应的 `action_id`。例如：

```text
[eye-bridge] received_at=15:59:33 action_id=eye.gentle source_event=manual_test session_id=manual-test duplicate=false
```

## 常见问题

### `Connection refused`

如果 RK3588 运行时报：

```text
[eye-bridge] fatal: [Errno 111] Connection refused
```

说明 RK3588 已经访问到本机电脑 IP，但本机电脑的 `1883` 端口没有 MQTT Broker 在监听。先在本机电脑安装并启动 Mosquitto，并确认它监听局域网地址。

## 第一阶段边界

- 暂不接入屏幕动画渲染
- 暂不处理助手回复文本
- 暂不启用 MQTT 账号密码
- 暂不启用 TLS

## 后续扩展

- 接入异显屏幕
- 增加表情到动画的映射
- 增加 systemd 服务
- 公网部署时启用 MQTT 账号密码和 TLS
