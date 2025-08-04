#!/usr/bin/env python3
"""
连接对象管理示例
模拟小智项目中的连接对象使用场景
"""

import asyncio
import threading
import queue
import time
import uuid
import json
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from enum import Enum
import copy

print("🔗 连接对象管理示例")
print("=" * 50)

# ===========================================
# 1. 基础连接对象
# ===========================================

class ConnectionState(Enum):
    """连接状态枚举"""
    CONNECTING = "connecting"
    CONNECTED = "connected"
    PROCESSING = "processing"
    DISCONNECTING = "disconnecting"
    DISCONNECTED = "disconnected"
    ERROR = "error"

@dataclass
class ConnectionConfig:
    """连接配置"""
    device_id: str
    client_ip: str
    audio_format: str = "opus"
    max_workers: int = 5
    timeout_seconds: int = 120
    intent_type: str = "intent_llm"
    
    # 模拟小智项目中的配置
    plugins: Dict[str, Any] = field(default_factory=dict)
    xiaozhi: Dict[str, Any] = field(default_factory=dict)
    exit_commands: List[str] = field(default_factory=lambda: ["退出", "拜拜", "再见"])

class BasicConnection:
    """基础连接对象"""
    
    def __init__(self, config: ConnectionConfig):
        # 基础属性
        self.config = config
        self.session_id = str(uuid.uuid4())
        self.device_id = config.device_id
        self.client_ip = config.client_ip
        
        # 状态管理
        self.state = ConnectionState.CONNECTING
        self.last_activity_time = time.time() * 1000
        self.connected_time = time.time()
        
        # 并发控制
        self.loop = asyncio.new_event_loop()
        self.executor = ThreadPoolExecutor(max_workers=config.max_workers)
        self.lock = threading.Lock()
        
        # 队列管理
        self.message_queue = queue.Queue()
        self.audio_queue = queue.Queue()
        
        print(f"🔌 创建连接: {self.device_id} (会话ID: {self.session_id[:8]})")
    
    def get_connection_info(self) -> Dict[str, Any]:
        """获取连接信息"""
        with self.lock:
            return {
                "session_id": self.session_id,
                "device_id": self.device_id,
                "client_ip": self.client_ip,
                "state": self.state.value,
                "connected_time": self.connected_time,
                "last_activity": self.last_activity_time,
                "queue_sizes": {
                    "message": self.message_queue.qsize(),
                    "audio": self.audio_queue.qsize()
                }
            }
    
    def update_state(self, new_state: ConnectionState):
        """更新连接状态"""
        with self.lock:
            old_state = self.state
            self.state = new_state
            print(f"🔄 连接 {self.device_id} 状态变化: {old_state.value} -> {new_state.value}")
    
    def cleanup(self):
        """清理连接资源"""
        print(f"🧹 清理连接 {self.device_id}")
        
        # 更新状态
        self.update_state(ConnectionState.DISCONNECTING)
        
        # 清理队列
        self._clear_queues()
        
        # 关闭线程池
        if self.executor:
            self.executor.shutdown(wait=False)
        
        # 更新状态
        self.update_state(ConnectionState.DISCONNECTED)
        
        print(f"✅ 连接 {self.device_id} 已清理")
    
    def _clear_queues(self):
        """清理队列"""
        queues = [self.message_queue, self.audio_queue]
        for q in queues:
            while not q.empty():
                try:
                    q.get_nowait()
                except queue.Empty:
                    break
        print(f"🧹 队列已清理")

def basic_connection_demo():
    """基础连接对象演示"""
    print("\n1️⃣ 基础连接对象")
    print("-" * 30)
    
    # 创建连接配置
    config = ConnectionConfig(
        device_id="ESP32_001",
        client_ip="192.168.1.100",
        audio_format="opus",
        max_workers=5
    )
    
    # 创建连接对象
    conn = BasicConnection(config)
    
    # 模拟连接生命周期
    conn.update_state(ConnectionState.CONNECTED)
    
    # 添加一些消息到队列
    conn.message_queue.put("hello")
    conn.message_queue.put("how are you")
    conn.audio_queue.put(b"audio_data_1")
    
    # 获取连接信息
    info = conn.get_connection_info()
    print(f"📋 连接信息: {json.dumps(info, indent=2, default=str)}")
    
    # 模拟处理状态
    conn.update_state(ConnectionState.PROCESSING)
    time.sleep(1)
    
    # 清理连接
    conn.cleanup()

# ===========================================
# 2. 模拟小智项目的连接处理器
# ===========================================

class MockAIService:
    """模拟AI服务"""
    def __init__(self, service_name: str):
        self.service_name = service_name
        self.model_name = f"Mock{service_name}"
    
    async def process(self, data: Any) -> Any:
        """处理数据"""
        await asyncio.sleep(0.1)  # 模拟处理时间
        return f"处理结果 from {self.service_name}"

class MockDialogue:
    """模拟对话管理"""
    def __init__(self):
        self.dialogue = []
    
    def add_message(self, role: str, content: str):
        """添加消息"""
        self.dialogue.append({"role": role, "content": content})
    
    def get_history(self) -> List[Dict]:
        """获取历史"""
        return self.dialogue.copy()

class XiaozhiConnection:
    """小智连接处理器"""
    
    def __init__(self, config: ConnectionConfig):
        # 基础连接属性
        self.config = copy.deepcopy(config)
        self.session_id = str(uuid.uuid4())
        self.device_id = config.device_id
        self.headers = {"device-id": config.device_id}
        
        # 状态管理
        self.state = ConnectionState.CONNECTING
        self.client_abort = False
        self.client_is_speaking = False
        self.client_listen_mode = "auto"
        self.close_after_chat = False
        
        # 并发控制
        self.loop = asyncio.new_event_loop()
        self.executor = ThreadPoolExecutor(max_workers=config.max_workers)
        self.stop_event = threading.Event()
        
        # 队列管理
        self.asr_audio_queue = queue.Queue()
        self.tts_text_queue = queue.Queue()
        self.tts_audio_queue = queue.Queue()
        self.report_queue = queue.Queue()
        
        # AI服务组件
        self.vad = MockAIService("VAD")
        self.asr = MockAIService("ASR")
        self.llm = MockAIService("LLM")
        self.tts = MockAIService("TTS")
        self.intent = MockAIService("Intent")
        self.memory = MockAIService("Memory")
        
        # 对话管理
        self.dialogue = MockDialogue()
        
        # 语音相关
        self.asr_audio = []
        self.sentence_id = None
        
        # 活动时间
        self.last_activity_time = time.time() * 1000
        
        print(f"🤖 创建小智连接: {self.device_id}")
    
    async def initialize(self):
        """初始化连接"""
        print(f"🔄 初始化连接 {self.device_id}")
        
        # 模拟组件初始化
        def init_components():
            time.sleep(0.5)  # 模拟初始化时间
            print(f"✅ 组件初始化完成: {self.device_id}")
        
        # 在线程池中初始化
        await asyncio.get_event_loop().run_in_executor(
            self.executor, init_components
        )
        
        self.update_state(ConnectionState.CONNECTED)
        print(f"🎉 连接 {self.device_id} 已就绪")
    
    def update_state(self, new_state: ConnectionState):
        """更新连接状态"""
        old_state = self.state
        self.state = new_state
        print(f"📊 {self.device_id} 状态: {old_state.value} -> {new_state.value}")
    
    async def handle_audio_message(self, audio_data: bytes):
        """处理音频消息"""
        self.last_activity_time = time.time() * 1000
        
        # 放入音频队列
        self.asr_audio_queue.put(audio_data)
        print(f"🎤 音频数据入队: {len(audio_data)} bytes")
        
        # 异步处理音频
        await self._process_audio_async(audio_data)
    
    async def _process_audio_async(self, audio_data: bytes):
        """异步处理音频"""
        # VAD检测
        has_voice = await self.vad.process(audio_data)
        
        if has_voice:
            print(f"🗣️ 检测到语音活动")
            self.asr_audio.append(audio_data)
            
            # 如果语音结束，进行识别
            if len(self.asr_audio) >= 5:  # 模拟语音结束条件
                await self._process_voice_recognition()
    
    async def _process_voice_recognition(self):
        """处理语音识别"""
        print(f"🔍 开始语音识别")
        
        # 合并音频数据
        combined_audio = b"".join(self.asr_audio)
        self.asr_audio.clear()
        
        # ASR识别
        text = await self.asr.process(combined_audio)
        print(f"📝 识别结果: {text}")
        
        # 添加到对话历史
        self.dialogue.add_message("user", text)
        
        # 意图识别
        intent = await self.intent.process(text)
        print(f"🎯 意图识别: {intent}")
        
        # 根据意图处理
        await self._handle_intent(intent, text)
    
    async def _handle_intent(self, intent: str, text: str):
        """处理意图"""
        if "继续聊天" in intent:
            # LLM生成回复
            await self._generate_llm_response(text)
        else:
            # 执行特定功能
            await self._execute_function(intent)
    
    async def _generate_llm_response(self, text: str):
        """生成LLM回复"""
        print(f"🤖 生成LLM回复")
        
        # 在线程池中执行LLM调用
        def llm_call():
            time.sleep(1)  # 模拟LLM处理时间
            return f"我理解了您说的 '{text}'，这是我的回复。"
        
        response = await asyncio.get_event_loop().run_in_executor(
            self.executor, llm_call
        )
        
        print(f"💬 LLM回复: {response}")
        
        # 添加到对话历史
        self.dialogue.add_message("assistant", response)
        
        # TTS合成
        await self._text_to_speech(response)
    
    async def _execute_function(self, intent: str):
        """执行函数"""
        print(f"⚙️ 执行函数: {intent}")
        
        # 在线程池中执行函数
        def function_call():
            time.sleep(0.5)  # 模拟函数执行时间
            return f"函数 {intent} 执行完成"
        
        result = await asyncio.get_event_loop().run_in_executor(
            self.executor, function_call
        )
        
        print(f"✅ 函数结果: {result}")
    
    async def _text_to_speech(self, text: str):
        """文本转语音"""
        print(f"🔊 TTS合成: {text}")
        
        # 放入TTS队列
        self.tts_text_queue.put(text)
        
        # 模拟TTS处理
        audio_data = await self.tts.process(text)
        self.tts_audio_queue.put(audio_data)
        
        print(f"🎵 TTS完成，音频数据: {len(str(audio_data))} chars")
    
    async def handle_text_message(self, message: str):
        """处理文本消息"""
        self.last_activity_time = time.time() * 1000
        
        print(f"📝 收到文本消息: {message}")
        
        # 根据消息类型处理
        if message == "hello":
            await self._send_welcome_message()
        elif message == "abort":
            self.client_abort = True
            print(f"🛑 客户端中止操作")
        else:
            # 直接处理为用户输入
            await self._process_user_input(message)
    
    async def _send_welcome_message(self):
        """发送欢迎消息"""
        welcome = "你好！我是小智助手，很高兴为您服务。"
        await self._text_to_speech(welcome)
    
    async def _process_user_input(self, text: str):
        """处理用户输入"""
        # 添加到对话历史
        self.dialogue.add_message("user", text)
        
        # 意图识别
        intent = await self.intent.process(text)
        
        # 处理意图
        await self._handle_intent(intent, text)
    
    def get_status(self) -> Dict[str, Any]:
        """获取连接状态"""
        return {
            "session_id": self.session_id,
            "device_id": self.device_id,
            "state": self.state.value,
            "client_abort": self.client_abort,
            "client_is_speaking": self.client_is_speaking,
            "last_activity": self.last_activity_time,
            "dialogue_count": len(self.dialogue.get_history()),
            "queue_sizes": {
                "asr_audio": self.asr_audio_queue.qsize(),
                "tts_text": self.tts_text_queue.qsize(),
                "tts_audio": self.tts_audio_queue.qsize(),
                "report": self.report_queue.qsize()
            }
        }
    
    async def cleanup(self):
        """清理连接"""
        print(f"🧹 开始清理连接 {self.device_id}")
        
        self.update_state(ConnectionState.DISCONNECTING)
        
        # 停止处理
        self.stop_event.set()
        self.client_abort = True
        
        # 保存记忆
        if self.memory:
            await self._save_memory()
        
        # 清理队列
        self._clear_all_queues()
        
        # 关闭线程池
        if self.executor:
            self.executor.shutdown(wait=False)
        
        self.update_state(ConnectionState.DISCONNECTED)
        print(f"✅ 连接 {self.device_id} 清理完成")
    
    async def _save_memory(self):
        """保存记忆"""
        print(f"💾 保存记忆: {len(self.dialogue.get_history())} 条对话")
        
        # 模拟保存记忆
        def save_task():
            time.sleep(0.2)
            return "记忆保存成功"
        
        result = await asyncio.get_event_loop().run_in_executor(
            self.executor, save_task
        )
        print(f"✅ {result}")
    
    def _clear_all_queues(self):
        """清理所有队列"""
        queues = [
            self.asr_audio_queue,
            self.tts_text_queue,
            self.tts_audio_queue,
            self.report_queue
        ]
        
        for q in queues:
            while not q.empty():
                try:
                    q.get_nowait()
                except queue.Empty:
                    break
        
        print(f"🧹 所有队列已清理")

async def xiaozhi_connection_demo():
    """小智连接演示"""
    print("\n\n2️⃣ 小智连接处理器")
    print("-" * 30)
    
    # 创建连接配置
    config = ConnectionConfig(
        device_id="ESP32_002",
        client_ip="192.168.1.101",
        audio_format="opus",
        max_workers=5,
        intent_type="intent_llm"
    )
    
    # 创建连接
    conn = XiaozhiConnection(config)
    
    # 初始化连接
    await conn.initialize()
    
    # 模拟消息处理
    await conn.handle_text_message("hello")
    await asyncio.sleep(0.5)
    
    await conn.handle_text_message("播放音乐")
    await asyncio.sleep(0.5)
    
    # 模拟音频处理
    audio_data = b"mock_audio_data" * 10
    await conn.handle_audio_message(audio_data)
    await asyncio.sleep(1)
    
    # 获取状态
    status = conn.get_status()
    print(f"📊 连接状态: {json.dumps(status, indent=2, default=str)}")
    
    # 清理连接
    await conn.cleanup()

# ===========================================
# 3. 连接管理器
# ===========================================

class ConnectionManager:
    """连接管理器"""
    
    def __init__(self):
        self.connections: Dict[str, XiaozhiConnection] = {}
        self.lock = threading.Lock()
    
    async def create_connection(self, config: ConnectionConfig) -> XiaozhiConnection:
        """创建连接"""
        with self.lock:
            if config.device_id in self.connections:
                # 关闭现有连接
                await self.remove_connection(config.device_id)
            
            # 创建新连接
            conn = XiaozhiConnection(config)
            await conn.initialize()
            self.connections[config.device_id] = conn
            
            print(f"📱 连接管理器: 新连接 {config.device_id} (总数: {len(self.connections)})")
            return conn
    
    async def remove_connection(self, device_id: str):
        """移除连接"""
        with self.lock:
            if device_id in self.connections:
                conn = self.connections.pop(device_id)
                await conn.cleanup()
                print(f"🗑️ 连接管理器: 移除连接 {device_id} (总数: {len(self.connections)})")
    
    def get_connection(self, device_id: str) -> Optional[XiaozhiConnection]:
        """获取连接"""
        with self.lock:
            return self.connections.get(device_id)
    
    def get_all_connections(self) -> List[XiaozhiConnection]:
        """获取所有连接"""
        with self.lock:
            return list(self.connections.values())
    
    async def cleanup_all(self):
        """清理所有连接"""
        print(f"🧹 清理所有连接: {len(self.connections)} 个")
        
        with self.lock:
            connections = list(self.connections.values())
            self.connections.clear()
        
        # 并发清理所有连接
        cleanup_tasks = [conn.cleanup() for conn in connections]
        await asyncio.gather(*cleanup_tasks)
        
        print(f"✅ 所有连接已清理")
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self.lock:
            stats = {
                "total_connections": len(self.connections),
                "connections_by_state": {},
                "active_connections": []
            }
            
            for device_id, conn in self.connections.items():
                state = conn.state.value
                stats["connections_by_state"][state] = stats["connections_by_state"].get(state, 0) + 1
                
                if conn.state == ConnectionState.CONNECTED:
                    stats["active_connections"].append({
                        "device_id": device_id,
                        "session_id": conn.session_id[:8],
                        "last_activity": conn.last_activity_time
                    })
            
            return stats

async def connection_manager_demo():
    """连接管理器演示"""
    print("\n\n3️⃣ 连接管理器")
    print("-" * 30)
    
    # 创建连接管理器
    manager = ConnectionManager()
    
    # 创建多个连接
    configs = [
        ConnectionConfig("ESP32_001", "192.168.1.100"),
        ConnectionConfig("ESP32_002", "192.168.1.101"),
        ConnectionConfig("ESP32_003", "192.168.1.102"),
    ]
    
    # 并发创建连接
    create_tasks = [manager.create_connection(config) for config in configs]
    connections = await asyncio.gather(*create_tasks)
    
    # 模拟一些活动
    for conn in connections:
        await conn.handle_text_message("hello")
    
    await asyncio.sleep(0.5)
    
    # 获取统计信息
    stats = manager.get_statistics()
    print(f"📊 连接统计: {json.dumps(stats, indent=2, default=str)}")
    
    # 移除一个连接
    await manager.remove_connection("ESP32_002")
    
    # 获取更新后的统计
    stats = manager.get_statistics()
    print(f"📊 更新后统计: {json.dumps(stats, indent=2, default=str)}")
    
    # 清理所有连接
    await manager.cleanup_all()

# ===========================================
# 主函数
# ===========================================

async def main():
    """主函数"""
    print("🚀 开始连接对象管理演示")
    
    # 运行基础演示
    basic_connection_demo()
    
    # 运行小智连接演示
    await xiaozhi_connection_demo()
    
    # 运行连接管理器演示
    await connection_manager_demo()
    
    print("\n" + "=" * 50)
    print("🎉 连接对象管理示例演示完成！")
    print("💡 关键要点:")
    print("   1. 连接对象封装了客户端的所有状态和资源")
    print("   2. 使用线程池和队列实现并发处理")
    print("   3. 连接管理器统一管理多个连接")
    print("   4. 合理的生命周期管理和资源清理")
    print("   5. 在小智项目中，每个ESP32设备对应一个连接对象")

if __name__ == "__main__":
    asyncio.run(main())