# 🤖 小智机器人运动控制完整实现指南

## 📖 概述

本指南展示如何在小智项目中添加机器人运动控制功能，使用服务端插件方式实现，支持语音控制机器人前进、后退、左转、右转、停止等功能。

## 🗂️ 已创建的文件

| 文件名 | 用途 |
|--------|------|
| `plugins_func/functions/robot_control.py` | 机器人控制插件主文件 |
| `examples/config_robot_addition.yaml` | 配置文件修改示例 |
| `examples/esp32_robot_control.cpp` | ESP32端完整代码 |
| `examples/robot_usage_example.md` | 使用指南和示例 |
| `examples/ROBOT_CONTROL_COMPLETE_GUIDE.md` | 本完整指南 |

## 🚀 快速开始

### **服务端插件方式实现**

**支持复杂功能，如序列运动控制**

#### **步骤1：确认插件文件**
确认 `plugins_func/functions/robot_control.py` 已存在

#### **步骤2：修改配置文件**
修改 `config.yaml` 添加函数列表（参考 `config_robot_addition.yaml`）

#### **步骤3：ESP32固件集成**
```cpp
// 复制 esp32_robot_control.cpp 中的以下函数到你的固件：
- handleRobotControlMessage()    // 消息处理
- executeRobotMove()            // 运动执行
- 电机控制相关函数
```

#### **步骤4：重启服务**
```bash
cd xiaozhi-server
python app.py
```

#### **步骤5：语音测试**
- 🗣️ "停止机器人"
- 🗣️ "让机器人前进2秒"  
- 🗣️ "机器人向左转"

## 🗣️ 支持的语音命令

### **基础控制**
- "让机器人前进"
- "机器人后退3秒"  
- "向左转"
- "向右转2秒，速度70"
- "停止机器人"
- "查询机器人状态"

### **高级控制（序列运动）**
- "让机器人前进2秒，然后左转1秒，再前进1秒，最后停止"
- "执行巡逻路线：前进3秒，右转2秒，前进2秒，左转2秒"

## 🔧 硬件连接示例

```
ESP32引脚连接：
GPIO2  -> 左电机正转
GPIO4  -> 左电机反转  
GPIO16 -> 右电机正转
GPIO17 -> 右电机反转
GPIO5  -> 左电机PWM（速度控制）
GPIO18 -> 右电机PWM（速度控制）
```

## 🛠️ 调试建议

### **1. 检查函数注册**
查看服务器启动日志，确认看到：
```
[INFO] 当前支持的函数列表: [..., robot_move, robot_sequence_move, ...]
```

### **2. 测试WebSocket连接**
ESP32串口应该显示：
```
机器人控制命令已发送：{"type":"robot_control",...}
WebSocket连接正常
```

### **3. 语音识别测试**
先测试简单命令：
- "停止机器人" （最基础，应该立即响应）
- "你支持哪些功能" （确认机器人控制工具已加载）

### **4. 常见问题解决**

| 问题 | 可能原因 | 解决方案 |
|------|----------|----------|
| 语音无响应 | 函数未注册 | 检查配置文件和重启服务 |
| ESP32无动作 | WebSocket连接问题 | 检查网络连接和消息格式 |
| 运动不准确 | 电机参数问题 | 调整PWM值和时间参数 |

## 🎨 扩展建议

### **传感器集成**
```python
# 在robot_control.py中添加
@register_function("robot_get_distance", robot_distance_desc, ToolType.SYSTEM_CTL)
def robot_get_distance(conn):
    """获取前方距离"""
    # 实现超声波传感器读取
```

### **智能功能**
```python
# 在robot_control.py中添加
@register_function("robot_patrol", robot_patrol_desc, ToolType.SYSTEM_CTL)
def robot_patrol(conn, area: str = "room"):
    """智能巡逻功能"""
    # 实现巡逻逻辑
```

### **安全功能**
```cpp
// 添加紧急停止
if (digitalRead(EMERGENCY_STOP_PIN) == LOW) {
    stopRobot();
    webSocket.sendTXT("{\"type\":\"emergency\",\"message\":\"紧急停止触发\"}");
}
```

## 📞 支持与反馈

如果遇到问题，请：
1. 查看服务器和ESP32的日志输出
2. 确认硬件连接正确
3. 验证网络连接状态
4. 检查配置文件格式

## 🎉 下一步

1. **硬件准备**：连接电机驱动和ESP32
2. **代码集成**：将示例代码集成到你的固件
3. **配置修改**：按照示例修改config.yaml
4. **测试验证**：从简单的停止命令开始测试
5. **功能扩展**：根据需求添加更多机器人功能

现在你已经有了完整的机器人控制解决方案，可以让小智语音助手控制机器人运动了！🚀