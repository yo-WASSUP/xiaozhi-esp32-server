# Tools 工具系统代码解读

> 本文解读工具系统的完整架构：五种工具类型、统一管理器、执行器模式、插件注册机制。

---

## 一、Tools 整体架构

```
core/providers/tools/
├── base/
│   ├── tool_types.py              # ToolType 枚举 + ToolDefinition 数据类
│   └── tool_executor.py           # ToolExecutor 抽象基类
├── unified_tool_manager.py        # ToolManager — 中央管理器（路由+缓存）
├── unified_tool_handler.py        # UnifiedToolHandler — 生命周期管理
│
├── server_plugins/                # ① 服务端插件（本地 Python 函数）
│   └── plugin_executor.py
├── server_mcp/                    # ② 服务端 MCP（stdio/SSE 协议）
│   ├── mcp_manager.py
│   ├── mcp_client.py
│   └── mcp_executor.py
├── device_iot/                    # ③ 设备端 IoT（ESP32 硬件控制）
│   ├── iot_executor.py
│   ├── iot_descriptor.py
│   └── iot_handler.py
├── device_mcp/                    # ④ 设备端 MCP（ESP32 MCP 协议）
│   ├── mcp_executor.py
│   ├── mcp_client.py
│   └── mcp_handler.py
└── mcp_endpoint/                  # ⑤ MCP 接入点（外部 WebSocket 服务）
    ├── mcp_endpoint_executor.py
    ├── mcp_endpoint_client.py
    └── mcp_endpoint_handler.py

plugins_func/                      # 插件函数注册系统
├── register.py                    # 注册装饰器 + 全局注册表
├── loadplugins.py                 # 自动导入所有插件模块
└── functions/                     # 具体的插件实现
    ├── get_time.py                # 查询时间/农历
    ├── get_weather.py             # 查询天气
    ├── handle_exit_intent.py      # 退出对话
    ├── play_music.py              # 播放音乐
    ├── change_role.py             # 切换角色
    ├── hass_get_state.py          # HA 查询设备状态
    ├── hass_set_state.py          # HA 控制设备
    ├── hass_play_music.py         # HA 播放音乐
    ├── hass_init.py               # HA 初始化提示词
    ├── ros2_robot_control.py      # ROS2 机器人控制
    ├── get_news_from_newsnow.py   # 新闻查询
    ├── get_news_from_chinanews.py # 中国新闻查询
    └── search_from_ragflow.py     # RAGFlow 知识库搜索
```

---

## 二、类型系统

### 2.1 `base/tool_types.py` — 工具类型定义

```python
class ToolType(Enum):
    SERVER_PLUGIN = "server_plugin"   # 服务端 Python 插件
    SERVER_MCP = "server_mcp"         # 服务端 MCP 协议工具
    DEVICE_IOT = "device_iot"         # 设备端 IoT 硬件控制
    DEVICE_MCP = "device_mcp"         # 设备端 MCP 协议工具
    MCP_ENDPOINT = "mcp_endpoint"     # 外部 MCP 接入点

@dataclass
class ToolDefinition:
    name: str                          # 工具名称
    description: Dict[str, Any]       # OpenAI function calling 格式描述
    tool_type: ToolType               # 所属类型
    parameters: Optional[Dict] = None # 额外参数
```

### 2.2 `base/tool_executor.py` — 执行器抽象基类

```python
class ToolExecutor(ABC):
    @abstractmethod
    async def execute(self, conn, tool_name, arguments) -> ActionResponse:
        """执行工具调用"""
    @abstractmethod
    def get_tools(self) -> Dict[str, ToolDefinition]:
        """获取该执行器管理的所有工具"""
    @abstractmethod
    def has_tool(self, tool_name) -> bool:
        """检查是否有指定工具"""
```

### 2.3 `plugins_func/register.py` — 插件注册系统

```python
# 插件函数的类型（与 tool_types.py 中的 ToolType 不同！）
class ToolType(Enum):
    NONE = (1, "调用完不做其他操作")
    WAIT = (2, "调用工具，等待返回")
    CHANGE_SYS_PROMPT = (3, "修改系统提示词")
    SYSTEM_CTL = (4, "系统控制，需要 conn 参数")
    IOT_CTL = (5, "IoT 设备控制，需要 conn 参数")
    MCP_CLIENT = (6, "MCP 客户端")

class Action(Enum):
    ERROR = (-1, "错误")
    NOTFOUND = (0, "没有找到函数")
    NONE = (1, "啥也不干")
    RESPONSE = (2, "直接回复用户")
    REQLLM = (3, "调用函数后再请求 LLM 生成回复")

class ActionResponse:
    action: Action      # 后续动作类型
    result: str         # 工具执行结果（传给 LLM 或日志）
    response: str       # 直接回复用户的文本

# 全局注册表
all_function_registry = {}

# 注册装饰器
@register_function("get_weather", description, ToolType.WAIT)
def get_weather(location="广州"):
    ...
    return ActionResponse(Action.REQLLM, result="晴天 25°C", response=None)
```

---

## 三、核心组件详解

### 3.1 `unified_tool_manager.py` — 中央管理器

ToolManager 是所有工具的统一入口，负责路由和缓存：

```python
class ToolManager:
    def __init__(self, conn):
        self.executors: Dict[ToolType, ToolExecutor] = {}   # 类型→执行器映射
        self._cached_tools = None                            # 工具定义缓存
        self._cached_function_descriptions = None            # OpenAI 格式描述缓存

    def register_executor(self, tool_type, executor):
        """注册执行器（注册后自动清除缓存）"""
        self.executors[tool_type] = executor
        self._invalidate_cache()

    def get_all_tools(self) -> Dict[str, ToolDefinition]:
        """聚合所有执行器的工具定义（带缓存）"""
        if self._cached_tools:
            return self._cached_tools
        all_tools = {}
        for tool_type, executor in self.executors.items():
            tools = executor.get_tools()
            for name, definition in tools.items():
                if name in all_tools:
                    logger.warning(f"工具名称冲突: {name}")
                all_tools[name] = definition
        self._cached_tools = all_tools
        return all_tools

    async def execute_tool(self, tool_name, arguments) -> ActionResponse:
        """路由到对应执行器执行"""
        tool_type = self.get_tool_type(tool_name)  # 查找工具属于哪个类型
        executor = self.executors[tool_type]         # 获取对应执行器
        return await executor.execute(self.conn, tool_name, arguments)
```

**路由流程：**
```
execute_tool("get_weather", {"location": "北京"})
    ↓
get_tool_type("get_weather") → ToolType.SERVER_PLUGIN
    ↓
executors[SERVER_PLUGIN] → ServerPluginExecutor
    ↓
ServerPluginExecutor.execute(conn, "get_weather", {"location": "北京"})
    ↓
ActionResponse(Action.REQLLM, result="晴天 25°C")
```

### 3.2 `unified_tool_handler.py` — 生命周期管理

UnifiedToolHandler 负责创建、初始化、调用、清理整个工具系统：

```python
class UnifiedToolHandler:
    def __init__(self, conn):
        self.tool_manager = ToolManager(conn)

        # 创建五种执行器
        self.server_plugin_executor = ServerPluginExecutor(conn)
        self.server_mcp_executor = ServerMCPExecutor(conn)
        self.device_iot_executor = DeviceIoTExecutor(conn)
        self.device_mcp_executor = DeviceMCPExecutor(conn)
        self.mcp_endpoint_executor = MCPEndpointExecutor(conn)

        # 注册到管理器
        self.tool_manager.register_executor(ToolType.SERVER_PLUGIN, ...)
        self.tool_manager.register_executor(ToolType.SERVER_MCP, ...)
        self.tool_manager.register_executor(ToolType.DEVICE_IOT, ...)
        self.tool_manager.register_executor(ToolType.DEVICE_MCP, ...)
        self.tool_manager.register_executor(ToolType.MCP_ENDPOINT, ...)
```

**初始化流程（`_initialize()`）：**

```
① auto_import_modules("plugins_func.functions")
   → 导入所有插件模块 → 触发 @register_function → 填充 all_function_registry

② await server_mcp_executor.initialize()
   → 读取 data/.mcp_server_settings.json
   → 为每个 MCP 服务器建立连接（stdio/SSE）

③ await _initialize_mcp_endpoint()
   → 连接外部 MCP 接入点 WebSocket

④ _initialize_home_assistant()
   → 将 HA 设备列表追加到系统提示词

⑤ current_support_functions()
   → 日志输出所有可用工具
```

**LLM 函数调用处理（`handle_llm_function_call()`）：**

```python
async def handle_llm_function_call(self, conn, function_call_data):
    # 支持多函数调用
    if "function_calls" in function_call_data:
        responses = []
        for call in function_call_data["function_calls"]:
            result = await self.tool_manager.execute_tool(call["name"], call["arguments"])
            responses.append(result)
        return self._combine_responses(responses)

    # 单函数调用
    function_name = function_call_data["name"]
    arguments = json.loads(function_call_data["arguments"])  # 字符串→字典
    return await self.tool_manager.execute_tool(function_name, arguments)
```

---

## 四、五种执行器详解

### 4.1 服务端插件（ServerPluginExecutor）

**工具来源：** `plugins_func/functions/` 下用 `@register_function` 装饰的 Python 函数

**执行逻辑：**
```python
async def execute(conn, tool_name, arguments):
    func_item = all_function_registry[tool_name]

    # 根据函数类型决定是否传 conn
    if func_item.type.code in [4, 5]:   # SYSTEM_CTL / IOT_CTL
        result = func_item.func(conn, **arguments)
    else:
        result = func_item.func(**arguments)

    return result  # ActionResponse
```

**工具发现：** 只暴露 config 中 `Intent[selected_module].functions` 列表里配置的函数。

**示例插件：**
```python
# plugins_func/functions/get_weather.py
@register_function("get_weather", get_weather_function_desc, ToolType.WAIT)
def get_weather(conn, location=None, response_success=None, response_failure=None):
    # 调用天气 API
    weather_info = qweather_api.get_weather(location)
    return ActionResponse(
        action=Action.REQLLM,
        result=f"{location}天气：{weather_info}",
        response=None   # 让 LLM 生成自然语言回复
    )
```

### 4.2 服务端 MCP（ServerMCPExecutor）

**工具来源：** `data/.mcp_server_settings.json` 中配置的 MCP 服务器

**架构：**
```
ServerMCPExecutor
    └─ ServerMCPManager
        ├─ ServerMCPClient ("server_a")  → stdio 进程
        ├─ ServerMCPClient ("server_b")  → SSE/HTTP 连接
        └─ ServerMCPClient ("server_c")  → stdio 进程
```

**配置示例：**
```json
{
  "mcpServers": {
    "my_tool_server": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-tools"],
      "timeout": 30
    },
    "remote_server": {
      "url": "http://localhost:8080/sse",
      "transport": "sse"
    }
  }
}
```

**特性：** 3 次重试、自动重连、10s 初始化超时、20s 清理超时。

### 4.3 设备端 IoT（DeviceIoTExecutor）

**工具来源：** ESP32 设备上报的 IoT 描述符（通过 WebSocket 消息动态注册）

**自动生成工具名：**
```
设备描述: { name: "灯", properties: { brightness: 100 }, methods: { turn_on: {} } }
    ↓
自动生成工具:
  - "get_灯_brightness"  → 查询亮度
  - "灯_turn_on"         → 打开灯
```

**执行方式：** 通过 WebSocket 发送控制命令到 ESP32 设备。

### 4.4 设备端 MCP（DeviceMCPExecutor）

**工具来源：** ESP32 设备通过 MCP 协议上报的工具列表

**执行方式：** JSON-RPC 格式通过 WebSocket 发送命令，等待设备响应（30s 超时）。

### 4.5 MCP 接入点（MCPEndpointExecutor）

**工具来源：** 外部 MCP 接入点服务（通过 WebSocket 连接）

**执行方式：** 类似设备端 MCP，但连接到云端或其他服务器。

---

## 五、工具执行完整流程

```
用户说: "北京天气怎么样"
    ↓
ASR → 文本
    ↓
Intent 识别 → {"function_call": {"name": "get_weather", "arguments": {"location": "北京"}}}
    ↓
intentHandler.process_intent_result()
    ↓
func_handler.handle_llm_function_call(conn, function_call_data)
    ↓
tool_manager.execute_tool("get_weather", {"location": "北京"})
    ├─ get_tool_type("get_weather") → SERVER_PLUGIN
    ├─ executors[SERVER_PLUGIN].execute(conn, "get_weather", {"location": "北京"})
    └─ get_weather(conn, location="北京")
        ├─ 调用和风天气 API
        └─ return ActionResponse(Action.REQLLM, result="北京 晴 25°C")
    ↓
Action.REQLLM → 将结果传给 LLM 生成自然语言
    ↓
LLM: "北京今天是晴天，气温 25 度，很适合出门"
    ↓
TTS → 语音播放
```

---

## 六、两套 ToolType 的关系

项目中有**两套 ToolType 枚举**，容易混淆：

| 位置 | 用途 | 值 |
|------|------|------|
| `core/providers/tools/base/tool_types.py` | **工具来源分类** | SERVER_PLUGIN, SERVER_MCP, DEVICE_IOT, DEVICE_MCP, MCP_ENDPOINT |
| `plugins_func/register.py` | **插件行为分类** | NONE, WAIT, CHANGE_SYS_PROMPT, SYSTEM_CTL, IOT_CTL, MCP_CLIENT |

**第一套**决定工具由哪个执行器处理（路由），**第二套**决定插件函数的调用方式（是否传 conn，是否等待返回）。

```
ToolManager 用第一套路由:
  get_weather → SERVER_PLUGIN → ServerPluginExecutor

ServerPluginExecutor 用第二套决定调用方式:
  get_weather → ToolType.WAIT(code=2) → 不传 conn，等待返回
  play_music  → ToolType.SYSTEM_CTL(code=4) → 传 conn，系统控制
```

---

## 七、Action 类型与后续处理

```python
class Action(Enum):
    ERROR = -1     # 执行出错 → TTS 朗读错误信息
    NOTFOUND = 0   # 工具未找到 → TTS 提示未找到
    NONE = 1       # 静默执行 → 不回复用户
    RESPONSE = 2   # 直接回复 → TTS 朗读 response 字段
    REQLLM = 3     # 需要润色 → result 传给 LLM → LLM 生成自然语言 → TTS
```

**REQLLM 是最常用的模式：** 工具返回结构化数据，LLM 将其转化为口语化回复。例如天气工具返回 `"北京 晴 25°C 风力3级"`，LLM 生成 `"北京今天是晴天，25度，微风，适合出门哦"`。

---

## 八、内置插件一览

| 插件 | 函数名 | 类型 | 说明 |
|------|--------|------|------|
| **get_time** | `get_time` / `get_lunar` | WAIT | 查询时间/农历 |
| **get_weather** | `get_weather` | WAIT | 和风天气 API |
| **handle_exit_intent** | `handle_exit_intent` | SYSTEM_CTL | 结束对话 |
| **play_music** | `play_music` | SYSTEM_CTL | 播放本地音乐 |
| **change_role** | `change_role` | CHANGE_SYS_PROMPT | 切换 AI 角色 |
| **hass_get_state** | `hass_get_state` | IOT_CTL | HA 查询设备状态 |
| **hass_set_state** | `hass_set_state` | IOT_CTL | HA 控制设备 |
| **hass_play_music** | `hass_play_music` | IOT_CTL | HA 播放音乐 |
| **ros2_robot_control** | `ros2_robot_move` | WAIT | ROS2 机器人控制 |
| **get_news** | `get_news_from_newsnow` | WAIT | 新闻查询 |
| **search_ragflow** | `search_from_ragflow` | WAIT | RAGFlow 知识库搜索 |

---

## 九、添加自定义工具的方法

### 方法 1：服务端插件（最简单）

在 `plugins_func/functions/` 下创建新文件：

```python
# plugins_func/functions/my_tool.py
from plugins_func.register import register_function, Action, ActionResponse, ToolType

my_tool_desc = {
    "type": "function",
    "function": {
        "name": "my_tool",
        "description": "我的自定义工具",
        "parameters": {
            "type": "object",
            "properties": {
                "param1": {"type": "string", "description": "参数1"}
            },
            "required": ["param1"]
        }
    }
}

@register_function("my_tool", my_tool_desc, ToolType.WAIT)
def my_tool(param1="default"):
    result = f"执行结果: {param1}"
    return ActionResponse(Action.REQLLM, result=result)
```

然后在 config.yaml 中启用：

```yaml
Intent:
  function_call:
    functions:
      - my_tool    # 添加你的工具名
```

### 方法 2：MCP 服务器

在 `data/.mcp_server_settings.json` 中添加：

```json
{
  "mcpServers": {
    "my_mcp_server": {
      "command": "python",
      "args": ["my_mcp_server.py"]
    }
  }
}
```

无需修改代码，MCP 工具自动发现和注册。
