# 小智服务器测试页面

## 文件结构

```
test/
├── index.html              # 重构后的主页面（推荐使用）
├── test_page.html          # 原始的大文件（备份保留）
├── assets/
│   ├── css/
│   │   └── main.css        # 样式文件
│   └── js/
│       ├── utils.js        # 工具函数和日志
│       ├── config.js       # 配置管理
│       ├── websocket.js    # WebSocket连接管理
│       ├── audio.js        # 音频处理
│       ├── ros2.js         # ROS2命令检测和执行
│       └── ui.js          # UI管理和事件处理
├── ros2_server/
│   ├── ros2_executor.js    # ROS2命令执行服务
│   ├── package.json        # 依赖配置
│   └── test_commands.txt   # 测试命令
└── libopus.js             # Opus音频编解码库
```

## 模块说明

### 1. utils.js - 工具模块
- 日志记录函数
- MAC地址生成
- Opus库检查
- 全局常量定义

### 2. config.js - 配置管理
- 设备配置获取和验证
- 配置面板交互
- 认证测试功能
- 标签页管理

### 3. websocket.js - WebSocket连接
- 连接管理
- 消息处理
- 状态管理
- 二进制数据发送

### 4. audio.js - 音频处理
- 音频录制
- 音频播放
- 可视化效果
- 缓冲管理

### 5. ros2.js - ROS2功能
- 命令检测（已修复正则表达式）
- 自动执行
- 命令显示
- 服务管理

### 6. ui.js - UI管理
- 页面初始化
- 事件绑定
- 消息显示
- 状态更新

## 使用方式

### 启动测试页面
1. 使用新版本：打开 `index.html`
2. 使用原版本：打开 `test_page.html`

### ROS2功能测试
1. 在Ubuntu环境启动ROS2执行服务：
   ```bash
   cd ros2_server
   npm install
   npm start
   ```

2. 在测试页面中说"机器人前进"等指令

3. 页面会自动检测ROS2命令并执行

### 主要改进

1. **模块化结构**：代码按功能拆分，易于维护
2. **修复了ROS2检测**：正则表达式支持JSON格式参数
3. **改进的错误处理**：更好的错误提示和日志
4. **清晰的依赖关系**：模块间依赖明确
5. **保留向后兼容**：原文件仍可使用

### 文件大小对比
- 原文件：2722行，~150KB
- 重构后：
  - index.html：~150行
  - 6个JS模块：各约100-200行
  - 1个CSS文件：~400行
  - 总计更易维护，功能更清晰

### 开发建议
- 修改样式：编辑 `assets/css/main.css`
- 添加功能：在对应的JS模块中扩展
- 新增模块：创建新的JS文件并在index.html中引入