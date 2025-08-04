# 机器人运动控制使用指南

## 📋 实现步骤总结

### **1. 已完成的文件**
- ✅ `plugins_func/functions/robot_control.py` - 机器人控制插件
- ✅ `examples/config_robot_addition.yaml` - 配置文件修改示例
- ✅ `examples/esp32_robot_control.cpp` - ESP32端代码示例

### **2. 需要手动操作的步骤**

#### **步骤1：修改配置文件**
在 `config.yaml` 中的 `Intent` 部分添加机器人控制函数：

```yaml
Intent:
  intent_llm:
    functions:
      - get_weather
      - get_news_from_newsnow  
      - play_music
      # 新增机器人控制函数
      - robot_move
      - robot_sequence_move
      - robot_get_status
      
  function_call:
    functions:
      - change_role
      - get_weather
      - get_news_from_newsnow
      - play_music
      # 新增机器人控制函数  
      - robot_move
      - robot_sequence_move
      - robot_get_status
```

#### **步骤2：ESP32固件集成**
将 `esp32_robot_control.cpp` 中的代码集成到你的ESP32固件中：
1. 添加电机控制引脚定义
2. 集成机器人控制函数
3. 在WebSocket消息处理中添加机器人控制处理

#### **步骤3：重启服务**
```bash
cd xiaozhi-server
python app.py
```

## 🎯 语音控制示例

### **基础运动控制**
- 🗣️ **"让机器人前进"** → 机器人前进1秒，速度50%
- 🗣️ **"机器人后退2秒"** → 机器人后退2秒
- 🗣️ **"向左转"** → 机器人左转1秒
- 🗣️ **"向右转3秒"** → 机器人右转3秒
- 🗣️ **"停止机器人"** → 机器人立即停止

### **序列运动控制**
- 🗣️ **"让机器人前进2秒，然后左转1秒，再前进1秒，最后停止"**
- 🗣️ **"执行巡逻路线：前进3秒，右转2秒，前进2秒，左转2秒"**

### **状态查询**
- 🗣️ **"机器人状态如何"** → 查询机器人当前状态
- 🗣️ **"检查机器人"** → 获取机器人状态信息

## 🔧 函数调用格式

### **robot_move**
```json
{
  "function_call": {
    "name": "robot_move",
    "arguments": {
      "direction": "forward",  // forward/backward/left/right/stop
      "duration": 2.0,         // 持续时间(秒)
      "speed": 70              // 速度(0-100)
    }
  }
}
```

### **robot_sequence_move**
```json
{
  "function_call": {
    "name": "robot_sequence_move", 
    "arguments": {
      "sequence": "前进2秒，左转1秒，前进1秒，停止",
      "speed": 60
    }
  }
}
```

### **robot_get_status**
```json
{
  "function_call": {
    "name": "robot_get_status",
    "arguments": {}
  }
}
```

## 📱 ESP32消息格式

### **发送到ESP32的控制命令**
```json
{
  "type": "robot_control",
  "command": {
    "action": "move",
    "direction": "forward",
    "duration": 2.0,
    "speed": 50
  }
}
```

### **序列运动命令**
```json
{
  "type": "robot_control",
  "command": {
    "action": "sequence",
    "sequence": [
      {"direction": "forward", "duration": 2.0},
      {"direction": "left", "duration": 1.0},
      {"direction": "forward", "duration": 1.0}
    ],
    "speed": 60
  }
}
```

### **ESP32返回的状态信息**
```json
{
  "type": "robot_status",
  "data": {
    "isMoving": true,
    "direction": "forward", 
    "speed": 50,
    "battery": 85
  }
}
```

## 🎨 自定义扩展

### **添加新的运动模式**
```python
# 在robot_control.py中添加新函数
@register_function("robot_dance", robot_dance_desc, ToolType.SYSTEM_CTL)
def robot_dance(conn, dance_type: str = "simple"):
    """让机器人跳舞"""
    # 实现跳舞逻辑
    pass
```

### **添加传感器读取**
```python
@register_function("robot_get_distance", robot_distance_desc, ToolType.SYSTEM_CTL) 
def robot_get_distance(conn):
    """获取机器人前方距离"""
    # 实现超声波传感器读取
    pass
```

## ⚠️ 注意事项

1. **安全第一**：确保机器人运动时周围环境安全
2. **电源管理**：监控电池电量，低电量时自动停止
3. **通信稳定**：确保WiFi连接稳定，避免控制中断
4. **参数验证**：严格验证运动参数，防止异常行为
5. **紧急停止**：实现紧急停止功能，可通过语音"停止机器人"立即停止

## 🔍 调试建议

1. **查看日志**：启动服务时观察插件加载日志
2. **测试函数**：先用配置的测试页面测试函数调用
3. **检查WebSocket**：确认ESP32与服务器的WebSocket连接正常
4. **逐步调试**：从简单的停止命令开始测试

## 🚀 下一步扩展

- **视觉导航**：集成摄像头实现视觉定位
- **语音反馈**：机器人执行动作时的语音确认
- **路径规划**：智能路径规划和避障
- **手势控制**：结合视觉识别实现手势控制
- **多机器人**：支持控制多个机器人