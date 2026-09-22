# RK3588 Eye Renderer

本目录用于存放运行在 RK3588 外接屏上的眼睛渲染器（Eye Renderer）代码。

## 第一阶段目标

- 使用 Chromium 全屏网页显示眼睛
- 使用原生 HTML / CSS / JavaScript 实现
- 连接 `ws://127.0.0.1:8765`
- 接收 Eye Bridge 推送的 `action_id`
- 把 `eye.attentive`、`eye.gentle`、`eye.calm`、`eye.concern`、`eye.warm_smile` 映射成可见眼睛状态
- 新双眼屏模组按单个 `1920x1080` 页面渲染，左半区显示左眼，右半区显示右眼
- 支持非对称眼睛表现，例如眨单眼、左右视线偏移、左右眼开合差异
- 已实现自动轻微游移，第一版通过瞳孔和高光位置变化表达低频、低幅度视线偏移
- 已实现与患者端 3D 熊猫一致的玻璃眼风格：深黑球面、青色下缘光圈、左上高光和柔和内阴影

## 支持的 action_id

| action_id | 当前显示状态 |
| --- | --- |
| `eye.calm` | 平静半闭眼 |
| `eye.attentive` | 专注睁眼 |
| `eye.speak` | 专注睁眼 |
| `eye.gentle` | 温和笑眼 |
| `eye.concern` | 担忧下压眼型 |
| `eye.warm_smile` | 更明显的笑眼 |

未知或空的 `action_id` 会回退为 `eye.calm`。

本地预览时可以通过查询参数直接选择初始表情，例如：

```text
http://127.0.0.1:8080/?expression=attentive
http://127.0.0.1:8080/?expression=warm_smile
```

## 3D 熊猫玻璃眼风格

Eye Renderer 参考患者端 3D 熊猫素材，在不改变 `action_id` 和 WebSocket 消息格式的前提下采用深色玻璃眼风格。

设计目标：

- 保留当前 `eye.calm`、`eye.attentive`、`eye.speak`、`eye.gentle`、`eye.concern`、`eye.warm_smile` 的语义
- 屏幕内绘制近圆形的深黑玻璃眼球
- 青色虹膜光圈集中在眼球下半圈，与软件中 3D 熊猫的眼睛一致
- 左上区域保留一主一辅两层反光，增强玻璃球面的体积感
- 眼球边缘使用低对比内阴影，适配机器人外部黑色眼眶
- 青色光圈亮度控制在低刺激范围内
- 动画继续保持低频、低幅度、平滑过渡
- 不引入写实熊猫脸、鼻子、嘴巴或复杂头像

第一版实现范围：

- CSS 已实现深黑球面、青色下缘光圈、玻璃高光、内阴影和眼皮遮罩
- JS 表情状态和 MQTT 协议保持不变
- Eye Bridge 和后端发布逻辑保持不变

表情表达规则：

- 主要通过眼皮遮罩、青色光圈亮度和虹膜位置表达差异，眼球始终保持立体形态
- `eye.calm`：与专注状态采用相同的完整睁眼和视线游移效果
- `eye.attentive`：完整睁眼，青色光圈更清晰
- `eye.speak`：保持睁眼，光圈随说话状态轻微呼吸
- `eye.gentle`：下眼皮抬起，形成轻微笑眼弧度
- `eye.concern`：上眼皮下压，双眼向内轻微倾斜
- `eye.warm_smile`：下眼皮进一步抬起，光圈更明亮柔和

状态切换与自动眨眼使用独立遮罩层。表情眼皮采用约 `720-780ms` 的缓动过渡，切换时视线先平滑回到中央，再恢复低频自动游移，避免眼皮和瞳孔同时跳变。

## 双眼屏显示映射

当前双眼屏模组在 RK3588 上识别为单个 `HDMI-1` 输出。`display-test.html` 已验证左侧物理屏显示页面左半区，右侧物理屏显示页面右半区。

测试命令：

```bash
DISPLAY=:0 chromium-browser --kiosk file:///home/orangepi/eye-renderer/display-test.html
```

渲染策略：

- 启动一个 Chromium 全屏页面
- 保持一个 WebSocket 连接
- 一个 `action_id` 驱动一个双眼状态
- 页面内部按左右分区控制眼睛位置、尺寸和动画
- 双眼状态内部可以分别设置左眼和右眼参数
- 第一阶段不扩展 MQTT 协议，左右眼差异由 Eye Renderer 的本地表情映射决定

### 非对称能力顺序

第一阶段先实现视线偏移：

- 左右眼在同一个双眼状态中共享视线方向
- 通过瞳孔和高光的位置变化表达看向左侧、右侧、上方、下方
- 视线偏移由 Eye Renderer 本地根据 `action_id` 和自动轻微游移决定
- 暂不把视线方向加入 MQTT 消息字段

自动轻微游移约束：

- 低频变化，避免持续快速扫视
- 低幅度变化，避免视觉刺激过强
- 表情切换时平滑过渡到新状态
- `eye.concern` 的游移幅度应比 `eye.attentive` 更小
- `eye.speak` 保留轻微视线微动，幅度应比 `eye.attentive` 更小
- `eye.calm` 可以保留更慢、更轻的游移

第一版默认幅度：

| action_id | 最大游移幅度 |
| --- | --- |
| `eye.attentive` | `10%` |
| `eye.speak` | `4%` |
| `eye.calm` | `3%` |
| `eye.concern` | `2%` |

`eye.gentle` 和 `eye.warm_smile` 先沿用温和笑眼的低幅度游移，实际幅度在实现时按屏幕观感微调。

第一版默认节奏：

- 每 `3-5` 秒选择一次新的视线目标点
- 目标点过渡时间为 `800-1200ms`
- 目标点应限制在当前 `action_id` 的最大游移幅度内

后续再评估眨单眼和左右眼开合差异。

## 运行方式

从仓库根目录把 Eye Renderer 同步到 RK3588：

```bash
scp -r hardware/rk3588/eye-renderer orangepi@192.168.1.101:/home/orangepi/
```

同步完成后，在 RK3588 上打开全屏网页：

```bash
DISPLAY=:0 chromium-browser --kiosk file:///home/orangepi/eye-renderer/index.html
```

新版双眼屏验证重点：

- 左侧物理屏只显示左眼
- 右侧物理屏只显示右眼
- 瞳孔和高光每 `3-5` 秒出现一次低幅度平滑游移
- `eye.speak` 的游移幅度小于 `eye.attentive`

如果要退出 Chromium，可以另开 SSH 执行：

```bash
pkill chromium
```

## 职责边界

- Eye Bridge 负责 MQTT 通信和 WebSocket 推送
- Eye Renderer 只负责显示眼睛动画
- 第一版暂不引入 React、Vite、Electron、Live2D 或 3D
