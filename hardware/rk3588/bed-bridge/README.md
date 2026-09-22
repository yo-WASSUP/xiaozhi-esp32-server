# RK3588 Bed Bridge

该服务运行在医疗床专用 RK3588 上，订阅医疗床动作 MQTT 消息，校验 `bed.*` 协议并发布接收状态。当前执行层预留在 `on_message` 中，可继续接入医疗床厂商 SDK、串口或 GPIO。

## Topic 与消息

- 设备 ID：`rk3588-bed-001`
- 指令：`robot/rk3588-bed-001/bed/cmd`
- 状态：`robot/rk3588-bed-001/bed/status`
- 指令 `type`：`bed.set`

示例：

```json
{
  "type": "bed.set",
  "device_id": "rk3588-bed-001",
  "session_id": "当前会话 ID",
  "source": "voice_example",
  "source_event": "voice_action",
  "event_time": "2026-09-02T12:00:00+08:00",
  "action_id": "bed.head.up",
  "module": "bed",
  "params": {}
}
```

## 部署

把目录复制到医疗床 RK3588，并在该设备上执行：

```bash
cd ~/bed-bridge
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python bed_bridge.py
```

默认连接本机 `127.0.0.1:1883`，对应后端 `hospice.robot_bed.broker_host` 填写这台医疗床 RK3588 的实际 IP。若 Broker 部署在其他主机，启动时传入 `--broker-host <BROKER_IP>`，后端也填写同一个 Broker 地址。

运行测试：

```bash
python -m unittest -v test_bed_bridge.py
```
