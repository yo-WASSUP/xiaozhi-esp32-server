# RK3588 硬件清单

本文记录 RK3588 OrangePi 原型阶段的硬件、网络和访问参数。后续新增外接屏幕、传感器、底盘或执行器时，继续在本文或本目录下补充。

本文负责记录硬件参数、通信方案和联调状态。Eye Bridge 程序的安装、运行和测试说明见 [Eye Bridge README](../../../hardware/rk3588/eye-bridge/README.md)，Arm Bridge 程序的安装、运行和测试说明见 [Arm Bridge README](../../../hardware/rk3588/arm-bridge/README.md)，Aroma Bridge 程序的安装、运行和测试说明见 [Aroma Bridge README](../../../hardware/rk3588/aroma-bridge/README.md)，医疗床程序说明见 [Bed Bridge README](../../../hardware/rk3588/bed-bridge/README.md)。

## 当前部署阶段

- 阶段：RK3588 眼睛、上肢、香薰与医疗床 MQTT 通信闭环验证
- 目标：`xiaozhi-server` 通过 MQTT 发布 `action_id=eye.xxx`，RK3588 上的眼睛桥接服务（Eye Bridge）订阅后打印动作和时间
- 目标：`xiaozhi-server` 通过 MQTT 发布 `action_id=arm.xxx`，RK3588 上的上肢桥接服务（Arm Bridge）订阅后打印动作、参数和时间
- 目标：`xiaozhi-server` 通过 MQTT 发布 `action_id=aroma.xxx`，RK3588 上的香薰桥接服务（Aroma Bridge）订阅后打印动作、参数和时间
- 目标：`xiaozhi-server` 通过独立 MQTT 连接发布 `action_id=bed.xxx`，医疗床专用 RK3588 上的 Bed Bridge 订阅、校验并回报状态
- 当前状态：手动 MQTT 测试已跑通，RK3588 可收到 `action_id=eye.gentle`
- 当前状态：尊严疗法真实流程已跑通，RK3588 可收到 `mode_started`、`turn_result`、`state_updated` 的眼睛动作
- 当前状态：Arm Bridge 第一版只接收、校验、打印和发布状态，暂不调用真实机械臂硬件
- 当前状态：Aroma Bridge 第一版只接收、校验、打印和发布状态，暂不调用真实香薰硬件
- 当前状态：Bed Bridge 已支持 12 个医疗床动作的接收、校验和状态回报，医疗床 RK3588 实际 IP 待填写
- 后续：通信稳定后，接入 Chromium 全屏网页眼睛渲染器
- 后续：上肢动作通信稳定后，在 Arm Bridge 内部接入 CAN、串口、厂商 SDK 或 ROS2
- Chromium 验证：`DISPLAY=:0 chromium-browser --kiosk about:blank` 已能正常打开全屏白页

## 本机电脑

- 角色：运行 `xiaozhi-server` 和第一阶段 MQTT Broker
- 操作系统：Ubuntu 22
- 网络位置：当前局域网

## RK3588 OrangePi

- 角色：眼睛显示节点（Eye Display Node）的运行主机
- 设备标识：`rk3588-eye-001`
- 硬件：RK3588 OrangePi Ultra
- 操作系统：Ubuntu 22.04.4 LTS (Jammy Jellyfish)
- 系统版本字段：
  - `VERSION_ID="22.04"`
  - `VERSION="22.04.4 LTS (Jammy Jellyfish)"`
- 网络位置：当前局域网
- 记录到的设备 IP：`192.168.1.101`
- 记录到的 SSH 地址：`orangepi@192.168.1.101`
- SSH 命令：

```bash
ssh orangepi@192.168.1.101
```

> 待确认：设备 IP `192.168.1.101` 和 SSH 地址 `192.168.1.101` 不一致。后续实际连通测试后，以可 SSH 连接并可访问 MQTT Broker 的地址为准。

## 代码同步到 RK3588

从仓库根目录执行，把 Eye Bridge、Arm Bridge、Aroma Bridge 和 Eye Renderer 同步到 RK3588 的 `orangepi` 用户目录：

```bash
scp -r hardware/rk3588/eye-bridge orangepi@192.168.1.101:/home/orangepi/
scp -r hardware/rk3588/arm-bridge orangepi@192.168.1.101:/home/orangepi/
scp -r hardware/rk3588/aroma-bridge orangepi@192.168.1.101:/home/orangepi/
scp -r hardware/rk3588/eye-renderer orangepi@192.168.1.101:/home/orangepi/
```

如果实际可连通地址不是 `192.168.1.101`，把命令里的 IP 替换为当前 RK3588 SSH 地址。

## 外接屏幕

当前屏幕为同屏显示，用于第一版 Eye Renderer 原型验证。后续会更换为异屏显示。

- 屏幕用途：眼睛表情显示
- 连接方式：HDMI
- 当前显示输出：`HDMI-1`
- 当前分辨率：`1024x768`
- 刷新率：
- 屏幕方向：横屏
- 是否作为独立显示器：否，当前为同屏
- Linux 识别到的显示名称：`HDMI-1`
- DISPLAY：`:0`
- 会话类型：`tty`
- 渲染方式：Chromium 全屏网页
- 浏览器路径：`/usr/bin/chromium-browser`
- Chromium 全屏验证命令：`DISPLAY=:0 chromium-browser --kiosk about:blank`
- Chromium 验证结果：已正常打开全屏白页；GPU/Vulkan 相关日志暂不影响第一阶段渲染验证

当前 `xrandr --query` 结果：

```text
Screen 0: minimum 320 x 200, current 1024 x 768, maximum 16384 x 16384
HDMI-1 connected 1024x768+0+0 (normal left inverted right x axis y axis) 0mm x 0mm
   1024x768      60.00*
   800x600       60.32    56.25
   848x480       60.00
   640x480       59.94
```

### 新双眼屏模组实测

新硬件为左右两块小屏，通过同一 RK3588 显示输出呈现。当前系统只识别到一个 `HDMI-1`，说明操作系统层面暂未看到两个独立显示器。

- 屏幕用途：左眼和右眼表情显示
- 连接方式：HDMI
- 当前显示输出：`HDMI-1`
- 当前分辨率：`1920x1080`
- 当前刷新率：`60.00`
- 是否作为独立显示器：系统只识别为单个 HDMI 显示输出
- 判断：优先按单个 `1920x1080` 画布内左右分区渲染，不按两个 X11 显示输出分别启动 Chromium
- 显示映射测试结果：通过；左侧物理屏显示红色 `LEFT`，右侧物理屏显示绿色 `RIGHT`
- Chromium 日志：GPU/Vulkan/video capability 相关日志存在，但页面正常显示，暂不影响当前 Chromium 渲染路线

新硬件 `DISPLAY=:0 xrandr --query` 结果：

```text
Screen 0: minimum 320 x 200, current 1920 x 1080, maximum 16384 x 16384
HDMI-1 connected 1920x1080+0+0 (normal left inverted right x axis y axis) 0mm x 0mm
   3840x2160     50.00    30.00    25.00    24.00    29.97    23.98
   1920x1080     60.00*   50.00    59.94    30.00    29.97
   1920x1080i    60.00    59.94
```

新硬件 `/sys/class/drm/` 结果：

```text
card0
card0-HDMI-A-1
card0-Writeback-1
card1
renderD128
renderD129
version
```

双眼屏显示映射测试：

```bash
DISPLAY=:0 chromium-browser --kiosk file:///home/orangepi/eye-renderer/display-test.html
```

通过条件：

- 左侧物理屏显示红色 `LEFT`，右侧物理屏显示绿色 `RIGHT`：当前硬件可按单个 `1920x1080` 画布实现左右眼分区渲染。
- 两块物理屏都显示完整的红绿 `LEFT/RIGHT` 页面：当前硬件处于镜像显示，不能直接用于左右眼差异化显示。
- 只有一块物理屏显示内容：需要继续检查屏线、屏控板供电和屏控板配置。

当前实测结论：

- 左侧物理屏显示红色 `LEFT`
- 右侧物理屏显示绿色 `RIGHT`
- 双眼拼接显示模组满足左右眼差异化显示要求
- Eye Renderer 已改为单页面双区域渲染，左半区承载左眼，右半区承载右眼
- 需要支持非对称眼睛表现，例如眨单眼、左右视线偏移和左右眼开合差异
- 第一阶段不扩展 MQTT 协议，左右眼差异由 Eye Renderer 本地表情映射决定
- 非对称能力先实现自动轻微游移，通过瞳孔和高光位置变化表达低频、低幅度视线偏移
- 第一版默认最大游移幅度：`eye.attentive` 10%，`eye.speak` 4%，`eye.calm` 3%，`eye.concern` 2%
- 第一版默认游移节奏：每 `3-5` 秒选择一次新目标点，过渡时间 `800-1200ms`

## 独立眼睛显示屏验证

目标形态：RK3588 使用独立物理显示输出承载患者可见的眼睛表情。若采用左右眼两块物理屏幕，硬件需要同时识别两个可用显示输出，并能把 Chromium 窗口固定到对应屏幕区域。

### 1. 确认系统识别到几个显示输出

在 RK3588 上执行：

```bash
DISPLAY=:0 xrandr --query
ls -1 /sys/class/drm/
```

通过条件：

- 单块独立眼睛显示屏：至少出现一个 `connected` 输出，且该输出可作为眼睛屏使用。
- 左右眼两块物理屏：至少出现两个 `connected` 输出，例如 `HDMI-1` 和 `HDMI-2`，或 `HDMI-1` 和 `DP-1`。
- 每个 `connected` 输出都要有目标分辨率和刷新率，例如 `1024x768 60.00`。

### 2. 确认能扩展显示，避免镜像同屏

示例命令，实际输出名和分辨率以 `xrandr --query` 为准：

```bash
DISPLAY=:0 xrandr --output HDMI-1 --mode 1024x768 --pos 0x0 --output HDMI-2 --mode 1024x768 --pos 1024x0
DISPLAY=:0 xrandr --query
```

通过条件：

- `xrandr --query` 中两个输出的坐标不同，例如 `1024x768+0+0` 和 `1024x768+1024+0`。
- 鼠标或窗口能移动到第二块屏幕区域。
- 两块屏显示内容可以不同。

### 3. 确认 Chromium 能固定到目标屏

单块独立眼睛显示屏示例：

```bash
DISPLAY=:0 chromium-browser --new-window --window-position=1024,0 --window-size=1024,768 --kiosk file:///home/orangepi/eye-renderer/index.html
```

左右眼两块物理屏示例：

```bash
DISPLAY=:0 chromium-browser --new-window --window-position=0,0 --window-size=1024,768 file:///home/orangepi/eye-renderer/index.html?eye=left
DISPLAY=:0 chromium-browser --new-window --window-position=1024,0 --window-size=1024,768 file:///home/orangepi/eye-renderer/index.html?eye=right
```

通过条件：

- Chromium 打开后位于指定物理屏。
- 全屏或窗口尺寸与屏幕分辨率一致。
- Eye Renderer 能继续连接 `ws://127.0.0.1:8765` 并响应 MQTT 表情指令。

### 4. 需要记录的实测结果

每次更换屏幕或线材后，记录：

- 屏幕数量：
- 每块屏的连接方式：
- Linux 输出名：
- 分辨率：
- 刷新率：
- 坐标：
- 是否镜像：
- Chromium 是否能固定到目标屏：
- 左右眼是否需要两块物理屏：

## 眼睛渲染计划

- 渲染器：Chromium 全屏网页
- Eye Renderer 代码位置：`hardware/rk3588/eye-renderer/`
- 技术栈：原生 HTML / CSS / JavaScript
- 运行位置：RK3588 外接屏
- 启动方式：`chromium-browser --kiosk file:///home/orangepi/eye-renderer/index.html`
- 第一阶段目标：把 `attentive`、`gentle`、`calm`、`concern`、`warm_smile` 映射成可见眼睛状态
- 第一版动画风格：极简几何眼睛，用 CSS 绘制两只眼睛、眼皮和轻量过渡动画
- 通信边界：Eye Bridge 继续负责 MQTT；Eye Renderer 只负责显示
- 本机通信：Eye Bridge 在 `ws://127.0.0.1:8765` 提供 WebSocket，Eye Renderer 连接该地址接收 `action_id`
- WebSocket 暴露范围：只监听 localhost，不暴露到局域网

### 当前 eye action_id 列表

当前有效值来自 `main/xiaozhi-server/core/robot_actions/contract.py` 的标准动作表。

| action_id | 来源 robot_action | 使用场景 | 当前 Eye Renderer 表现 |
| --- | --- | --- | --- |
| `eye.calm` | `idle`、`pause` | 空闲、暂停、模式停止 | 平静半闭眼 |
| `eye.attentive` | `listening` | 倾听、继续深入、尊严疗法进行中 | 专注睁眼 |
| `eye.speak` | 系统说话状态 | 机器人说话时 | 专注睁眼，保留比 `eye.attentive` 更小幅度的视线微动 |
| `eye.gentle` | `comfort` | 安抚、承接低落情绪、安全改写 | 温和笑眼 |
| `eye.concern` | `nurse_alert` | 护士提醒、风险交接、需要人工关注 | 担忧下压眼型 |
| `eye.warm_smile` | `happy` | 积极、温暖、轻松的回应 | 更明显的笑眼 |

补充说明：

- MQTT 指令里只发送 `action_id` 和必要上下文字段，不发送助手回复文本。
- Eye Renderer 当前支持上表 6 个值。
- Eye Renderer 收到未知值时会回退到 `eye.calm`，保证屏幕仍有可显示状态。
- 代码里历史默认状态曾出现 `soft_smile`，当前硬件渲染阶段以标准 `eye.xxx` 动作为准。

### 眼睛动画风格优化路线

第一版只验证屏幕状态切换，不追求最终视觉效果。后续按阶段优化：

- 阶段 1：增加自动眨眼、轻微呼吸感和状态切换过渡
- 阶段 2：根据患者反馈调整颜色、眼型、亮度和运动幅度，避免过度刺激
- 阶段 3：补充更多表情细节，例如关切、倾听、安抚时的不同眼皮弧度
- 阶段 4：如果需要更强拟人感，再评估 SVG 分层动画、Canvas、Live2D 或 3D

## MQTT 通信计划

- 第一阶段 Broker 位置：本机电脑
- 第一阶段 Broker 软件：Mosquitto
- 后端 MQTT 客户端库：`paho-mqtt`
- RK3588 Eye Bridge 语言：Python
- RK3588 Eye Bridge 代码位置：`hardware/rk3588/eye-bridge/`
- 第一阶段 RK3588 行为：运行 Eye Bridge，订阅眼睛表情指令并打印 `action_id`、`event_time` 和 `received_at`
- 后端发布者：`xiaozhi-server`
- 订阅者：RK3588 Eye Bridge
- 设备标识：`rk3588-eye-001`
- 指令主题：`robot/rk3588-eye-001/eye/cmd`
- 状态主题：`robot/rk3588-eye-001/eye/status`
- RK3588 Arm Bridge 语言：Python
- RK3588 Arm Bridge 代码位置：`hardware/rk3588/arm-bridge/`
- 第一阶段 Arm Bridge 行为：订阅上肢动作指令并打印 `action_id`、`params`、`event_time` 和 `received_at`
- 上肢动作指令主题：`robot/rk3588-eye-001/arm/cmd`
- 上肢动作状态主题：`robot/rk3588-eye-001/arm/status`
- RK3588 Aroma Bridge 语言：Python
- RK3588 Aroma Bridge 代码位置：`hardware/rk3588/aroma-bridge/`
- 第一阶段 Aroma Bridge 行为：订阅香薰动作指令并打印 `action_id`、`params`、`event_time` 和 `received_at`
- 香薰动作指令主题：`robot/rk3588-eye-001/aroma/cmd`
- 香薰动作状态主题：`robot/rk3588-eye-001/aroma/status`
- 第一阶段认证：局域网内暂不启用账号密码
- 公网阶段要求：启用账号密码、TLS 和 topic 权限限制

### 后端配置位置

眼睛 MQTT 发布配置放在 `main/xiaozhi-server/data/.config_hospice.yaml` 的 `hospice.robot_eye` 下，默认关闭：

```yaml
hospice:
  robot_eye:
    enabled: false
    device_id: rk3588-eye-001
    # 可选；留空时默认使用 xiaozhi-server-{device_id}-eye
    # client_id: xiaozhi-server-rk3588-eye-001-eye
    broker_host: 192.168.1.100
    broker_port: 1883
    command_topic: robot/rk3588-eye-001/eye/cmd
    status_topic: robot/rk3588-eye-001/eye/status
    username: ""
    password: ""
    tls: false
    connect_timeout_seconds: 2.0
```

上肢 MQTT 发布配置放在 `hospice.robot_arm` 下，默认关闭：

```yaml
hospice:
  robot_arm:
    enabled: false
    device_id: rk3588-eye-001
    # 可选；留空时默认使用 xiaozhi-server-{device_id}-arm
    # client_id: xiaozhi-server-rk3588-eye-001-arm
    broker_host: 192.168.1.100
    broker_port: 1883
    command_topic: robot/rk3588-eye-001/arm/cmd
    status_topic: robot/rk3588-eye-001/arm/status
    username: ""
    password: ""
    tls: false
    connect_timeout_seconds: 2.0
```

香薰 MQTT 发布配置放在 `hospice.robot_aroma` 下，默认关闭：

```yaml
hospice:
  robot_aroma:
    enabled: false
    device_id: rk3588-eye-001
    broker_host: 192.168.1.100
    broker_port: 1883
    command_topic: robot/rk3588-eye-001/aroma/cmd
    status_topic: robot/rk3588-eye-001/aroma/status
    username: ""
    password: ""
    tls: false
```

医疗床使用另一台 RK3588 和独立 MQTT 连接，配置放在 `hospice.robot_bed` 下：

```yaml
hospice:
  robot_bed:
    enabled: false
    device_id: rk3588-bed-001
    # 替换为医疗床 RK3588 的实际 IP
    broker_host: BED_RK3588_IP
    broker_port: 1883
    command_topic: robot/rk3588-bed-001/bed/cmd
    status_topic: robot/rk3588-bed-001/bed/status
    username: ""
    password: ""
    tls: false
```

第一阶段跑通链路时，把对应模块的 `enabled` 改成 `true`。公网阶段再启用账号密码和 TLS。

### 后端发布器行为

- 采用懒连接：第一次需要发布眼睛表情时再连接 Mosquitto
- 连接失败只记录日志，`xiaozhi-server` 继续运行
- 发布失败只记录日志，患者对话和 TTS 继续执行
- 后续再次产生眼睛表情指令时，再重试连接和发布
- 上肢动作发布器同样采用懒连接、失败只记录日志、后续动作再重试
- Eye 与 Arm 发布器使用不同的 MQTT `client_id`；发布前等待连接就绪，缓存连接断开后自动重连
- 香薰动作发布器同样采用懒连接、失败只记录日志、后续动作再重试
- `system.stop` 会转换为 `aroma.stop` 发布，确保全局停止覆盖香薰模块
- 医疗床发布器使用独立 `broker_host`、设备 ID、client ID 和 topic，连接另一台 RK3588
- `system.stop` 会向医疗床发布 `bed.head.stop` 和 `bed.feet.stop`

### 第一阶段指令字段

指令消息不携带助手回复文本。第一阶段只传递眼睛显示需要的字段：

```json
{
  "type": "eye.set",
  "device_id": "rk3588-eye-001",
  "session_id": "当前会话 ID",
  "source": "dignity",
  "source_event": "turn_result",
  "event_time": "2026-06-23T15:59:32+08:00",
  "action_id": "eye.gentle",
  "origin_action_id": "eye.gentle",
  "robot_action": "comfort"
}
```

上肢动作指令沿用相同元数据字段，`type` 为 `arm.set`：

```json
{
  "type": "arm.set",
  "device_id": "rk3588-eye-001",
  "session_id": "当前会话 ID",
  "source": "voice_example",
  "source_event": "voice_action",
  "event_time": "2026-07-08T12:00:00+08:00",
  "action_id": "arm.wave",
  "module": "arm",
  "params": {
    "side": "right",
    "repeat": 1,
    "duration_ms": 1500
  }
}
```

香薰动作指令的 `type` 为 `aroma.set`：

```json
{
  "type": "aroma.set",
  "device_id": "rk3588-eye-001",
  "session_id": "当前会话 ID",
  "source": "voice_example",
  "source_event": "voice_action",
  "event_time": "2026-07-22T12:00:00+08:00",
  "action_id": "aroma.start",
  "module": "aroma",
  "params": {
    "type": "1",
    "duration_ms": 60000
  }
}
```

香薰 `duration_ms` 默认值为 `60000`，有效范围为 `1000`～`1800000`（最长 30 分钟）；正整数越界时会限幅到有效范围。

### 失败处理原则

- RK3588 掉线时，患者对话和 TTS 继续执行
- MQTT Broker 不可用时，服务端记录日志并继续当前对话
- MQTT 发布失败时，服务端记录日志并继续当前对话
- 机器人动作事件使用 `INFO`；MQTT 调度与发布成功使用 `DEBUG`；发布失败使用 `WARNING`
- Eye Bridge 收到缺失或无法识别的 `action_id` 时，记录日志并保持当前表情或回到默认表情
- Eye Bridge 收到重复 `action_id` 时，继续发布状态，但不再推送给 Eye Renderer，减少无意义屏幕刷新
- Arm Bridge 收到缺失或无法识别的 `action_id` 时，记录日志并发布带 `last_error` 的状态
- 第一版 Arm Bridge 不调用真实硬件；后续接入 CAN 时，在 Arm Bridge 内部增加执行层
- Aroma Bridge 收到缺失、无法识别或参数非法的指令时，记录日志并发布带 `last_error` 的状态
- 第一版 Aroma Bridge 不调用真实硬件，也不执行自动关闭倒计时；后续在 Bridge 内部增加执行层

### 后端真实流程没有表情消息时的检查项

- 确认 `main/xiaozhi-server/data/.config_hospice.yaml` 中 `hospice.robot_eye.enabled` 为 `true`
- 确认 `xiaozhi-server` 已在修改配置和代码后重启
- 确认启动 `xiaozhi-server` 的 Python 环境已安装 `paho-mqtt`
- 确认后端运行在包含 `core/dignity/robot_eye.py` 的分支或提交上
- 确认 RK3588 Eye Bridge 仍在订阅 `robot/rk3588-eye-001/eye/cmd`
- 如果平板端仍然没有触发真实流程，尝试在平板应用管理中清除缓存后重新进入

### 后端真实流程没有上肢动作消息时的检查项

- 确认 `main/xiaozhi-server/data/.config_hospice.yaml` 中 `hospice.robot_arm.enabled` 为 `true`
- 确认 `xiaozhi-server` 已在修改配置和代码后重启
- 确认启动 `xiaozhi-server` 的 Python 环境已安装 `paho-mqtt`
- 确认 RK3588 Arm Bridge 仍在订阅 `robot/rk3588-eye-001/arm/cmd`
- 确认语音日志里已经出现 `机器人动作事件: action_id=arm.wave, module=arm, status=accepted`
- 如果显式配置了 `client_id`，确认 `robot_eye` 和 `robot_arm` 的值不同

### 后端真实流程没有香薰动作消息时的检查项

- 确认 `main/xiaozhi-server/data/.config_hospice.yaml` 中 `hospice.robot_aroma.enabled` 为 `true`
- 确认 `xiaozhi-server` 已在修改配置和代码后重启
- 确认启动 `xiaozhi-server` 的 Python 环境已安装 `paho-mqtt`
- 确认 RK3588 Aroma Bridge 仍在订阅 `robot/rk3588-eye-001/aroma/cmd`
- 确认语音日志里已经出现 `机器人动作事件: action_id=aroma.start, module=aroma, status=accepted`

### 第一阶段状态回报

Eye Bridge 启动后，向状态主题发布一次 `online`：

```json
{
  "type": "eye.status",
  "device_id": "rk3588-eye-001",
  "online": true,
  "current_action_id": null,
  "last_error": null
}
```

Arm Bridge 启动后，向状态主题发布一次 `online`：

```json
{
  "type": "arm.status",
  "device_id": "rk3588-eye-001",
  "online": true,
  "current_action_id": null,
  "current_params": {},
  "last_error": null
}
```

Arm Bridge 每次收到指令后，向状态主题发布当前上肢动作：

```json
{
  "type": "arm.status",
  "device_id": "rk3588-eye-001",
  "online": true,
  "current_action_id": "arm.wave",
  "current_params": {
    "side": "right",
    "repeat": 1,
    "duration_ms": 1500
  },
  "last_error": null
}
```

Aroma Bridge 启动后，向状态主题发布一次 `online`，每次收到指令后更新当前动作与参数：

```json
{
  "type": "aroma.status",
  "device_id": "rk3588-eye-001",
  "online": true,
  "current_action_id": "aroma.start",
  "current_params": {
    "type": "1",
    "duration_ms": 60000
  },
  "last_error": null
}
```

Eye Bridge 每次收到指令后，向状态主题发布当前眼睛动作：

```json
{
  "type": "eye.status",
  "device_id": "rk3588-eye-001",
  "online": true,
  "current_action_id": "eye.gentle",
  "last_error": null
}
```
