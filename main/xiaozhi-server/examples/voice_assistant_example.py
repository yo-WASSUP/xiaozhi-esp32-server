#!/usr/bin/env python3
"""
语音助手综合应用示例
结合所有技术实现一个完整的语音助手处理流程
"""

import asyncio
import threading
import queue
import time
import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass
from enum import Enum
import websockets
import logging

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

print("🎙️ 语音助手综合应用示例")
print("=" * 50)

# ===========================================
# 1. 数据结构定义
# ===========================================

class MessageType(Enum):
    """消息类型"""
    AUDIO = "audio"
    TEXT = "text"
    HELLO = "hello"
    ABORT = "abort"
    GOODBYE = "goodbye"

class ProcessingState(Enum):
    """处理状态"""
    IDLE = "idle"
    RECEIVING_AUDIO = "receiving_audio"
    PROCESSING_ASR = "processing_asr"
    PROCESSING_INTENT = "processing_intent"
    PROCESSING_LLM = "processing_llm"
    PROCESSING_TTS = "processing_tts"
    SENDING_RESPONSE = "sending_response"

@dataclass
class AudioMessage:
    """音频消息"""
    data: bytes
    timestamp: float
    has_voice: bool = False

@dataclass
class IntentResult:
    """意图识别结果"""
    intent_type: str
    function_name: str
    arguments: Dict[str, Any]
    confidence: float

@dataclass
class ProcessingResult:
    """处理结果"""
    success: bool
    result: Any
    error: Optional[str] = None
    processing_time: float = 0

# ===========================================
# 2. 模拟AI服务组件
# ===========================================

class MockVADService:
    """模拟语音活动检测服务"""
    
    def __init__(self):
        self.name = "MockVAD"
        self.sensitivity = 0.5
    
    async def detect_voice_activity(self, audio_data: bytes) -> bool:
        """检测语音活动"""
        await asyncio.sleep(0.01)  # 模拟处理延迟
        # 简单的模拟逻辑：音频数据长度大于阈值认为有语音
        return len(audio_data) > 100

class MockASRService:
    """模拟语音识别服务"""
    
    def __init__(self):
        self.name = "MockASR"
        self.model = "whisper-large"
        self.sample_texts = [
            "你好小智",
            "播放音乐",
            "查询天气",
            "设置提醒",
            "打开灯光",
            "关闭空调",
            "我想听故事",
            "今天几点了"
        ]
    
    async def speech_to_text(self, audio_data: bytes) -> str:
        """语音转文本"""
        start_time = time.time()
        
        # 模拟ASR处理时间
        await asyncio.sleep(1.0)
        
        # 随机选择一个文本结果
        import random
        text = random.choice(self.sample_texts)
        
        processing_time = time.time() - start_time
        logger.info(f"ASR处理完成: '{text}' (耗时: {processing_time:.2f}s)")
        
        return text

class MockIntentService:
    """模拟意图识别服务"""
    
    def __init__(self):
        self.name = "MockIntent"
        self.model = "intent-classifier"
        self.intent_mapping = {
            "你好": {"intent": "greeting", "function": "handle_greeting"},
            "播放音乐": {"intent": "play_music", "function": "play_music"},
            "查询天气": {"intent": "get_weather", "function": "get_weather"},
            "设置提醒": {"intent": "set_reminder", "function": "set_reminder"},
            "打开灯光": {"intent": "control_device", "function": "control_light"},
            "关闭空调": {"intent": "control_device", "function": "control_ac"},
            "听故事": {"intent": "play_story", "function": "play_story"},
            "几点了": {"intent": "get_time", "function": "get_time"},
        }
    
    async def detect_intent(self, text: str) -> IntentResult:
        """检测意图"""
        start_time = time.time()
        
        # 模拟意图识别处理时间
        await asyncio.sleep(0.5)
        
        # 查找匹配的意图
        for keyword, intent_info in self.intent_mapping.items():
            if keyword in text:
                result = IntentResult(
                    intent_type=intent_info["intent"],
                    function_name=intent_info["function"],
                    arguments={"query": text},
                    confidence=0.95
                )
                processing_time = time.time() - start_time
                logger.info(f"意图识别完成: {result.intent_type} (耗时: {processing_time:.2f}s)")
                return result
        
        # 默认为聊天意图
        result = IntentResult(
            intent_type="chat",
            function_name="chat",
            arguments={"query": text},
            confidence=0.8
        )
        
        processing_time = time.time() - start_time
        logger.info(f"意图识别完成: {result.intent_type} (耗时: {processing_time:.2f}s)")
        return result

class MockLLMService:
    """模拟大语言模型服务"""
    
    def __init__(self):
        self.name = "MockLLM"
        self.model = "gpt-4"
        self.responses = {
            "greeting": "你好！我是小智助手，很高兴为您服务！",
            "chat": "我理解了您的话，这是我的回复。",
            "weather": "今天天气晴朗，温度适宜，很适合出行。",
            "time": f"现在是{time.strftime('%H:%M')}。",
            "default": "抱歉，我还没有理解您的意思，您能换个方式说吗？"
        }
    
    async def generate_response(self, intent: IntentResult, context: List[Dict]) -> str:
        """生成回复"""
        start_time = time.time()
        
        # 模拟LLM处理时间
        await asyncio.sleep(1.5)
        
        # 根据意图生成回复
        if intent.intent_type in self.responses:
            response = self.responses[intent.intent_type]
        else:
            response = self.responses["default"]
        
        processing_time = time.time() - start_time
        logger.info(f"LLM响应生成完成: '{response}' (耗时: {processing_time:.2f}s)")
        
        return response

class MockTTSService:
    """模拟文本转语音服务"""
    
    def __init__(self):
        self.name = "MockTTS"
        self.voice = "xiaozhi"
        self.speed = 1.0
    
    async def text_to_speech(self, text: str) -> bytes:
        """文本转语音"""
        start_time = time.time()
        
        # 模拟TTS处理时间
        await asyncio.sleep(0.8)
        
        # 生成模拟音频数据
        audio_data = f"<TTS_AUDIO:{text}>".encode() * 10
        
        processing_time = time.time() - start_time
        logger.info(f"TTS合成完成: {len(audio_data)} bytes (耗时: {processing_time:.2f}s)")
        
        return audio_data

class MockFunctionService:
    """模拟功能服务"""
    
    def __init__(self):
        self.name = "MockFunctions"
        self.functions = {
            "play_music": self.play_music,
            "get_weather": self.get_weather,
            "set_reminder": self.set_reminder,
            "control_light": self.control_light,
            "control_ac": self.control_ac,
            "play_story": self.play_story,
            "get_time": self.get_time,
            "handle_greeting": self.handle_greeting,
        }
    
    async def execute_function(self, function_name: str, arguments: Dict[str, Any]) -> str:
        """执行功能函数"""
        if function_name in self.functions:
            return await self.functions[function_name](arguments)
        else:
            return "抱歉，我不知道如何执行这个功能。"
    
    async def play_music(self, args: Dict) -> str:
        await asyncio.sleep(0.5)
        return "好的，正在为您播放音乐。"
    
    async def get_weather(self, args: Dict) -> str:
        await asyncio.sleep(0.3)
        return "今天北京天气晴朗，温度20度，适合出行。"
    
    async def set_reminder(self, args: Dict) -> str:
        await asyncio.sleep(0.2)
        return "提醒已设置成功，我会按时提醒您。"
    
    async def control_light(self, args: Dict) -> str:
        await asyncio.sleep(0.1)
        return "灯光已打开。"
    
    async def control_ac(self, args: Dict) -> str:
        await asyncio.sleep(0.1)
        return "空调已关闭。"
    
    async def play_story(self, args: Dict) -> str:
        await asyncio.sleep(0.3)
        return "好的，我来为您讲一个故事..."
    
    async def get_time(self, args: Dict) -> str:
        await asyncio.sleep(0.1)
        return f"现在是{time.strftime('%H点%M分')}。"
    
    async def handle_greeting(self, args: Dict) -> str:
        await asyncio.sleep(0.1)
        return "你好！我是小智助手，很高兴为您服务！"

# ===========================================
# 3. 语音助手连接处理器
# ===========================================

class VoiceAssistantConnection:
    """语音助手连接处理器"""
    
    def __init__(self, device_id: str, websocket=None):
        # 基础信息
        self.device_id = device_id
        self.session_id = str(uuid.uuid4())
        self.websocket = websocket
        self.state = ProcessingState.IDLE
        
        # 并发控制
        self.executor = ThreadPoolExecutor(max_workers=5)
        self.loop = asyncio.get_event_loop()
        
        # 队列管理
        self.audio_queue = queue.Queue()
        self.text_queue = queue.Queue()
        self.response_queue = queue.Queue()
        
        # AI服务组件
        self.vad = MockVADService()
        self.asr = MockASRService()
        self.intent = MockIntentService()
        self.llm = MockLLMService()
        self.tts = MockTTSService()
        self.functions = MockFunctionService()
        
        # 状态管理
        self.is_processing = False
        self.conversation_history = []
        self.audio_buffer = []
        
        # 处理线程
        self.processing_thread = None
        self.stop_event = threading.Event()
        
        logger.info(f"创建语音助手连接: {device_id}")
    
    async def start(self):
        """启动连接处理"""
        self.is_processing = True
        self.processing_thread = threading.Thread(target=self._run_processing_loop)
        self.processing_thread.start()
        logger.info(f"语音助手连接 {self.device_id} 已启动")
    
    def stop(self):
        """停止连接处理"""
        self.is_processing = False
        self.stop_event.set()
        if self.processing_thread:
            self.processing_thread.join()
        if self.executor:
            self.executor.shutdown(wait=False)
        logger.info(f"语音助手连接 {self.device_id} 已停止")
    
    def _run_processing_loop(self):
        """运行处理循环"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            loop.run_until_complete(self._processing_loop())
        finally:
            loop.close()
    
    async def _processing_loop(self):
        """处理循环"""
        while self.is_processing:
            try:
                # 处理音频队列
                await self._process_audio_queue()
                
                # 处理文本队列
                await self._process_text_queue()
                
                # 处理响应队列
                await self._process_response_queue()
                
                await asyncio.sleep(0.1)  # 避免忙等待
                
            except Exception as e:
                logger.error(f"处理循环出错: {e}")
                await asyncio.sleep(0.5)
    
    async def handle_message(self, message_type: MessageType, data: Any):
        """处理消息"""
        logger.info(f"收到消息: {message_type.value}")
        
        if message_type == MessageType.AUDIO:
            await self._handle_audio_message(data)
        elif message_type == MessageType.TEXT:
            await self._handle_text_message(data)
        elif message_type == MessageType.HELLO:
            await self._handle_hello_message()
        elif message_type == MessageType.ABORT:
            await self._handle_abort_message()
        elif message_type == MessageType.GOODBYE:
            await self._handle_goodbye_message()
    
    async def _handle_audio_message(self, audio_data: bytes):
        """处理音频消息"""
        audio_msg = AudioMessage(
            data=audio_data,
            timestamp=time.time()
        )
        self.audio_queue.put(audio_msg)
        logger.info(f"音频消息入队: {len(audio_data)} bytes")
    
    async def _handle_text_message(self, text: str):
        """处理文本消息"""
        self.text_queue.put(text)
        logger.info(f"文本消息入队: {text}")
    
    async def _handle_hello_message(self):
        """处理问候消息"""
        response = "你好！我是小智助手，很高兴为您服务！"
        await self._send_response(response)
    
    async def _handle_abort_message(self):
        """处理中止消息"""
        logger.info("用户中止操作")
        self.state = ProcessingState.IDLE
        self.audio_buffer.clear()
    
    async def _handle_goodbye_message(self):
        """处理再见消息"""
        response = "再见！期待下次为您服务！"
        await self._send_response(response)
    
    async def _process_audio_queue(self):
        """处理音频队列"""
        while not self.audio_queue.empty():
            try:
                audio_msg = self.audio_queue.get_nowait()
                await self._process_audio_message(audio_msg)
            except queue.Empty:
                break
    
    async def _process_text_queue(self):
        """处理文本队列"""
        while not self.text_queue.empty():
            try:
                text = self.text_queue.get_nowait()
                await self._process_text_input(text)
            except queue.Empty:
                break
    
    async def _process_response_queue(self):
        """处理响应队列"""
        while not self.response_queue.empty():
            try:
                response = self.response_queue.get_nowait()
                await self._send_response(response)
            except queue.Empty:
                break
    
    async def _process_audio_message(self, audio_msg: AudioMessage):
        """处理音频消息"""
        # VAD检测
        has_voice = await self.vad.detect_voice_activity(audio_msg.data)
        audio_msg.has_voice = has_voice
        
        if has_voice:
            self.audio_buffer.append(audio_msg)
            self.state = ProcessingState.RECEIVING_AUDIO
            logger.info(f"检测到语音，缓冲区大小: {len(self.audio_buffer)}")
        else:
            if self.audio_buffer:
                # 语音结束，开始处理
                await self._process_voice_buffer()
            else:
                logger.info("静音片段，跳过处理")
    
    async def _process_voice_buffer(self):
        """处理语音缓冲区"""
        if not self.audio_buffer:
            return
        
        self.state = ProcessingState.PROCESSING_ASR
        logger.info(f"开始处理语音缓冲区: {len(self.audio_buffer)} 个片段")
        
        # 合并音频数据
        combined_audio = b"".join([msg.data for msg in self.audio_buffer])
        self.audio_buffer.clear()
        
        # 在线程池中执行语音识别
        future = self.executor.submit(
            asyncio.run,
            self._complete_voice_processing(combined_audio)
        )
        
        # 不等待结果，继续处理其他消息
        logger.info("语音处理已提交到线程池")
    
    async def _complete_voice_processing(self, audio_data: bytes):
        """完成语音处理"""
        try:
            # ASR语音识别
            self.state = ProcessingState.PROCESSING_ASR
            text = await self.asr.speech_to_text(audio_data)
            
            # 处理识别结果
            await self._process_text_input(text)
            
        except Exception as e:
            logger.error(f"语音处理出错: {e}")
            self.state = ProcessingState.IDLE
    
    async def _process_text_input(self, text: str):
        """处理文本输入"""
        logger.info(f"开始处理文本输入: {text}")
        
        # 添加到对话历史
        self.conversation_history.append({"role": "user", "content": text})
        
        try:
            # 意图识别
            self.state = ProcessingState.PROCESSING_INTENT
            intent = await self.intent.detect_intent(text)
            
            if intent.intent_type == "chat":
                # 聊天意图，使用LLM生成回复
                await self._process_chat_intent(intent)
            else:
                # 功能意图，执行对应功能
                await self._process_function_intent(intent)
                
        except Exception as e:
            logger.error(f"文本处理出错: {e}")
            error_response = "抱歉，我遇到了一些问题，请稍后再试。"
            await self._send_response(error_response)
        finally:
            self.state = ProcessingState.IDLE
    
    async def _process_chat_intent(self, intent: IntentResult):
        """处理聊天意图"""
        self.state = ProcessingState.PROCESSING_LLM
        logger.info("处理聊天意图")
        
        # 生成LLM回复
        response = await self.llm.generate_response(intent, self.conversation_history)
        
        # 添加到对话历史
        self.conversation_history.append({"role": "assistant", "content": response})
        
        # 发送回复
        await self._send_response(response)
    
    async def _process_function_intent(self, intent: IntentResult):
        """处理功能意图"""
        logger.info(f"处理功能意图: {intent.function_name}")
        
        # 执行功能
        result = await self.functions.execute_function(
            intent.function_name, 
            intent.arguments
        )
        
        # 发送结果
        await self._send_response(result)
    
    async def _send_response(self, text: str):
        """发送响应"""
        self.state = ProcessingState.PROCESSING_TTS
        logger.info(f"开始发送响应: {text}")
        
        # TTS合成
        audio_data = await self.tts.text_to_speech(text)
        
        # 发送音频响应
        self.state = ProcessingState.SENDING_RESPONSE
        await self._send_audio_response(audio_data)
        
        logger.info("响应发送完成")
        self.state = ProcessingState.IDLE
    
    async def _send_audio_response(self, audio_data: bytes):
        """发送音频响应"""
        if self.websocket:
            try:
                await self.websocket.send(audio_data)
                logger.info(f"音频响应已发送: {len(audio_data)} bytes")
            except Exception as e:
                logger.error(f"发送音频响应失败: {e}")
        else:
            logger.info(f"模拟发送音频响应: {len(audio_data)} bytes")
    
    def get_status(self) -> Dict[str, Any]:
        """获取连接状态"""
        return {
            "device_id": self.device_id,
            "session_id": self.session_id,
            "state": self.state.value,
            "conversation_count": len(self.conversation_history),
            "audio_buffer_size": len(self.audio_buffer),
            "queue_sizes": {
                "audio": self.audio_queue.qsize(),
                "text": self.text_queue.qsize(),
                "response": self.response_queue.qsize()
            }
        }

# ===========================================
# 4. 语音助手服务器
# ===========================================

class VoiceAssistantServer:
    """语音助手服务器"""
    
    def __init__(self, host="localhost", port=8765):
        self.host = host
        self.port = port
        self.connections: Dict[str, VoiceAssistantConnection] = {}
        self.server = None
        
        logger.info(f"创建语音助手服务器: {host}:{port}")
    
    async def start(self):
        """启动服务器"""
        self.server = await websockets.serve(
            self.handle_connection,
            self.host,
            self.port
        )
        logger.info(f"语音助手服务器已启动: ws://{self.host}:{self.port}")
    
    async def stop(self):
        """停止服务器"""
        if self.server:
            self.server.close()
            await self.server.wait_closed()
        
        # 关闭所有连接
        for conn in self.connections.values():
            conn.stop()
        
        logger.info("语音助手服务器已停止")
    
    async def handle_connection(self, websocket, path):
        """处理WebSocket连接"""
        device_id = f"device_{len(self.connections) + 1}"
        logger.info(f"新连接: {device_id} from {websocket.remote_address}")
        
        # 创建连接处理器
        conn = VoiceAssistantConnection(device_id, websocket)
        self.connections[device_id] = conn
        
        try:
            # 启动连接处理
            await conn.start()
            
            # 发送欢迎消息
            await conn.handle_message(MessageType.HELLO, None)
            
            # 处理消息循环
            async for message in websocket:
                if isinstance(message, bytes):
                    # 音频消息
                    await conn.handle_message(MessageType.AUDIO, message)
                elif isinstance(message, str):
                    # 文本消息
                    if message == "abort":
                        await conn.handle_message(MessageType.ABORT, None)
                    elif message == "goodbye":
                        await conn.handle_message(MessageType.GOODBYE, None)
                    else:
                        await conn.handle_message(MessageType.TEXT, message)
                        
        except websockets.exceptions.ConnectionClosed:
            logger.info(f"连接关闭: {device_id}")
        except Exception as e:
            logger.error(f"连接处理出错: {e}")
        finally:
            # 清理连接
            if device_id in self.connections:
                self.connections[device_id].stop()
                del self.connections[device_id]
            logger.info(f"连接已清理: {device_id}")

# ===========================================
# 5. 演示客户端
# ===========================================

class MockClient:
    """模拟客户端"""
    
    def __init__(self, device_id: str):
        self.device_id = device_id
        self.websocket = None
        self.is_connected = False
    
    async def connect(self, uri: str):
        """连接到服务器"""
        try:
            self.websocket = await websockets.connect(uri)
            self.is_connected = True
            logger.info(f"客户端 {self.device_id} 已连接")
            
            # 启动消息接收
            asyncio.create_task(self._receive_messages())
            
        except Exception as e:
            logger.error(f"连接失败: {e}")
    
    async def disconnect(self):
        """断开连接"""
        if self.websocket:
            await self.websocket.close()
            self.is_connected = False
            logger.info(f"客户端 {self.device_id} 已断开")
    
    async def send_text(self, text: str):
        """发送文本消息"""
        if self.websocket:
            await self.websocket.send(text)
            logger.info(f"客户端 {self.device_id} 发送文本: {text}")
    
    async def send_audio(self, audio_data: bytes):
        """发送音频消息"""
        if self.websocket:
            await self.websocket.send(audio_data)
            logger.info(f"客户端 {self.device_id} 发送音频: {len(audio_data)} bytes")
    
    async def _receive_messages(self):
        """接收服务器消息"""
        try:
            while self.is_connected:
                message = await self.websocket.recv()
                if isinstance(message, bytes):
                    logger.info(f"客户端 {self.device_id} 收到音频: {len(message)} bytes")
                else:
                    logger.info(f"客户端 {self.device_id} 收到文本: {message}")
        except websockets.exceptions.ConnectionClosed:
            logger.info(f"客户端 {self.device_id} 连接已关闭")
        except Exception as e:
            logger.error(f"接收消息出错: {e}")

# ===========================================
# 6. 主演示程序
# ===========================================

async def run_demo():
    """运行演示"""
    print("\n🚀 启动语音助手综合演示")
    print("-" * 50)
    
    # 创建服务器
    server = VoiceAssistantServer()
    
    try:
        # 启动服务器
        await server.start()
        
        # 等待服务器启动
        await asyncio.sleep(0.5)
        
        # 创建模拟客户端
        client = MockClient("ESP32_001")
        await client.connect("ws://localhost:8765")
        
        # 等待连接建立
        await asyncio.sleep(1)
        
        # 模拟语音交互
        print("\n🎙️ 模拟语音交互:")
        
        # 发送文本消息
        await client.send_text("你好小智")
        await asyncio.sleep(2)
        
        await client.send_text("播放音乐")
        await asyncio.sleep(2)
        
        await client.send_text("查询天气")
        await asyncio.sleep(2)
        
        # 发送音频消息
        print("\n🎵 模拟音频交互:")
        audio_data = b"mock_audio_data_hello" * 20
        await client.send_audio(audio_data)
        await asyncio.sleep(3)
        
        audio_data = b"mock_audio_data_music" * 15
        await client.send_audio(audio_data)
        await asyncio.sleep(3)
        
        # 发送再见消息
        await client.send_text("goodbye")
        await asyncio.sleep(1)
        
        # 断开客户端
        await client.disconnect()
        
    except Exception as e:
        logger.error(f"演示运行出错: {e}")
    finally:
        # 停止服务器
        await server.stop()

async def run_simple_demo():
    """运行简单演示（不需要WebSocket）"""
    print("\n🎯 简单语音助手演示")
    print("-" * 50)
    
    # 创建连接处理器
    conn = VoiceAssistantConnection("ESP32_DEMO")
    
    try:
        # 启动连接
        await conn.start()
        
        # 模拟交互
        print("\n💬 模拟对话:")
        
        # 文本交互
        await conn.handle_message(MessageType.TEXT, "你好小智")
        await asyncio.sleep(2)
        
        await conn.handle_message(MessageType.TEXT, "播放音乐")
        await asyncio.sleep(2)
        
        await conn.handle_message(MessageType.TEXT, "现在几点了")
        await asyncio.sleep(2)
        
        # 音频交互
        print("\n🎤 模拟音频处理:")
        audio_data = b"mock_audio_weather_query" * 30
        await conn.handle_message(MessageType.AUDIO, audio_data)
        await asyncio.sleep(3)
        
        # 显示状态
        status = conn.get_status()
        print(f"\n📊 连接状态: {json.dumps(status, indent=2)}")
        
    finally:
        # 停止连接
        conn.stop()

async def main():
    """主函数"""
    print("🎙️ 语音助手综合应用演示")
    print("=" * 50)
    
    try:
        # 运行简单演示
        await run_simple_demo()
        
        print("\n" + "=" * 50)
        print("🎉 语音助手综合应用演示完成！")
        print("💡 关键特性展示:")
        print("   1. ✅ 线程池处理耗时任务")
        print("   2. ✅ 异步处理音频和文本消息")
        print("   3. ✅ 队列缓冲音频数据")
        print("   4. ✅ 连接对象管理会话状态")
        print("   5. ✅ 完整的语音助手处理流程")
        print("   6. ✅ 模拟真实的AI服务组件")
        
    except KeyboardInterrupt:
        print("\n⚠️ 用户中断演示")
    except Exception as e:
        print(f"\n❌ 演示出错: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())