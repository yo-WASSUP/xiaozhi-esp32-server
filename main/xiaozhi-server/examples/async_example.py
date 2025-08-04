#!/usr/bin/env python3
"""
异步编程使用示例
模拟小智项目中的异步编程场景
"""

import asyncio
import time
import json
import uuid
from typing import List, Dict

print("⚡ 异步编程使用示例")
print("=" * 50)

# ===========================================
# 1. 基础异步编程
# ===========================================

async def simple_async_task(name: str, duration: float) -> str:
    """简单的异步任务"""
    print(f"异步任务 {name} 开始执行，预计耗时 {duration} 秒")
    await asyncio.sleep(duration)  # 异步等待
    result = f"异步任务 {name} 完成！"
    print(f"✅ {result}")
    return result

async def basic_async_demo():
    """基础异步编程演示"""
    print("\n1️⃣ 基础异步编程")
    print("-" * 30)
    
    # 顺序执行
    print("📋 顺序执行:")
    start_time = time.time()
    await simple_async_task("任务1", 1)
    await simple_async_task("任务2", 1)
    await simple_async_task("任务3", 1)
    sequential_time = time.time() - start_time
    print(f"⏱️ 顺序执行耗时: {sequential_time:.2f} 秒")
    
    print("\n📋 并发执行:")
    start_time = time.time()
    # 并发执行
    tasks = [
        simple_async_task("任务A", 1),
        simple_async_task("任务B", 1),
        simple_async_task("任务C", 1)
    ]
    results = await asyncio.gather(*tasks)
    concurrent_time = time.time() - start_time
    print(f"⏱️ 并发执行耗时: {concurrent_time:.2f} 秒")
    print(f"🚀 性能提升: {sequential_time/concurrent_time:.2f}x")
    
    return results

# ===========================================
# 2. 模拟WebSocket消息处理
# ===========================================

class MockWebSocket:
    """模拟WebSocket连接"""
    def __init__(self, client_id: str):
        self.client_id = client_id
        self.is_open = True
        self.message_queue = []
    
    async def send(self, message: str):
        """发送消息"""
        if not self.is_open:
            raise Exception("WebSocket连接已关闭")
        
        await asyncio.sleep(0.1)  # 模拟网络延迟
        print(f"📤 向客户端 {self.client_id} 发送: {message}")
    
    async def receive(self):
        """接收消息"""
        if not self.is_open:
            raise Exception("WebSocket连接已关闭")
        
        # 模拟接收消息
        await asyncio.sleep(0.5)
        if self.message_queue:
            return self.message_queue.pop(0)
        return None
    
    def add_message(self, message: str):
        """添加模拟消息"""
        self.message_queue.append(message)
    
    def close(self):
        """关闭连接"""
        self.is_open = False

async def handle_websocket_client(websocket: MockWebSocket):
    """处理WebSocket客户端连接"""
    print(f"🔗 客户端 {websocket.client_id} 连接建立")
    
    try:
        while websocket.is_open:
            # 异步接收消息
            message = await websocket.receive()
            
            if message:
                print(f"📥 收到客户端 {websocket.client_id} 消息: {message}")
                
                # 模拟消息处理
                await asyncio.sleep(0.2)
                
                # 异步发送响应
                response = f"收到消息: {message}"
                await websocket.send(response)
            else:
                # 没有消息时短暂等待
                await asyncio.sleep(0.1)
                
    except Exception as e:
        print(f"❌ 客户端 {websocket.client_id} 处理出错: {e}")
    finally:
        print(f"🔚 客户端 {websocket.client_id} 连接关闭")

async def websocket_demo():
    """WebSocket异步处理演示"""
    print("\n\n2️⃣ 模拟WebSocket消息处理")
    print("-" * 30)
    
    # 创建多个模拟客户端
    clients = [
        MockWebSocket("ESP32_001"),
        MockWebSocket("ESP32_002"),
        MockWebSocket("ESP32_003")
    ]
    
    # 添加模拟消息
    clients[0].add_message("你好，小智")
    clients[1].add_message("播放音乐")
    clients[2].add_message("查询天气")
    
    # 并发处理多个客户端
    tasks = [handle_websocket_client(client) for client in clients]
    
    # 设置超时时间
    try:
        await asyncio.wait_for(asyncio.gather(*tasks), timeout=3.0)
    except asyncio.TimeoutError:
        print("⏰ 演示超时，关闭所有连接")
        for client in clients:
            client.close()

# ===========================================
# 3. 模拟语音处理流程
# ===========================================

class MockVAD:
    """模拟语音活动检测"""
    async def detect_voice(self, audio_data: bytes) -> bool:
        """检测语音活动"""
        await asyncio.sleep(0.01)  # 模拟VAD处理时间
        # 模拟检测结果
        return len(audio_data) > 100

class MockASR:
    """模拟语音识别"""
    async def transcribe(self, audio_data: bytes) -> str:
        """语音转文本"""
        await asyncio.sleep(1.0)  # 模拟ASR处理时间
        # 模拟识别结果
        texts = ["你好小智", "播放音乐", "查询天气", "设置提醒"]
        import random
        return random.choice(texts)

class MockLLM:
    """模拟大语言模型"""
    async def generate_response(self, text: str) -> str:
        """生成回复"""
        await asyncio.sleep(1.5)  # 模拟LLM处理时间
        return f"我理解了您说的'{text}'，这是我的回复。"

class MockTTS:
    """模拟文本转语音"""
    async def synthesize(self, text: str) -> bytes:
        """文本转语音"""
        await asyncio.sleep(0.8)  # 模拟TTS处理时间
        # 模拟音频数据
        return f"<audio_data_for:{text}>".encode()

async def voice_processing_pipeline(audio_data: bytes):
    """语音处理管道"""
    print(f"🎤 开始处理语音数据 (长度: {len(audio_data)} bytes)")
    
    # 创建组件
    vad = MockVAD()
    asr = MockASR()
    llm = MockLLM()
    tts = MockTTS()
    
    try:
        # 1. VAD检测
        has_voice = await vad.detect_voice(audio_data)
        if not has_voice:
            print("🔇 未检测到语音活动")
            return None
        
        print("🗣️ 检测到语音活动")
        
        # 2. ASR识别
        text = await asr.transcribe(audio_data)
        print(f"📝 语音识别结果: {text}")
        
        # 3. LLM生成回复
        response = await llm.generate_response(text)
        print(f"🤖 LLM生成回复: {response}")
        
        # 4. TTS合成
        audio_response = await tts.synthesize(response)
        print(f"🔊 TTS合成完成: {len(audio_response)} bytes")
        
        return {
            "input_text": text,
            "response_text": response,
            "audio_response": audio_response
        }
        
    except Exception as e:
        print(f"❌ 语音处理出错: {e}")
        return None

async def voice_demo():
    """语音处理演示"""
    print("\n\n3️⃣ 模拟语音处理流程")
    print("-" * 30)
    
    # 模拟多个语音输入
    audio_inputs = [
        b"mock_audio_data_1" * 20,
        b"mock_audio_data_2" * 15,
        b"mock_audio_data_3" * 25
    ]
    
    # 并发处理多个语音输入
    tasks = [voice_processing_pipeline(audio) for audio in audio_inputs]
    
    # 使用asyncio.gather并发执行
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # 处理结果
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            print(f"❌ 语音 {i+1} 处理失败: {result}")
        elif result:
            print(f"✅ 语音 {i+1} 处理成功: {result['input_text']} -> {result['response_text']}")
        else:
            print(f"🔇 语音 {i+1} 未检测到活动")

# ===========================================
# 4. 异步上下文管理器
# ===========================================

class AsyncConnectionManager:
    """异步连接管理器"""
    def __init__(self, connection_id: str):
        self.connection_id = connection_id
        self.is_connected = False
    
    async def __aenter__(self):
        """异步进入上下文"""
        print(f"🔌 建立连接: {self.connection_id}")
        await asyncio.sleep(0.1)  # 模拟连接建立时间
        self.is_connected = True
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步退出上下文"""
        print(f"🔚 关闭连接: {self.connection_id}")
        await asyncio.sleep(0.1)  # 模拟连接关闭时间
        self.is_connected = False
        
        if exc_type:
            print(f"❌ 连接 {self.connection_id} 发生异常: {exc_val}")
        return False  # 不抑制异常
    
    async def send_data(self, data: str):
        """发送数据"""
        if not self.is_connected:
            raise Exception("连接未建立")
        
        await asyncio.sleep(0.1)  # 模拟发送时间
        print(f"📤 连接 {self.connection_id} 发送: {data}")

async def async_context_demo():
    """异步上下文管理器演示"""
    print("\n\n4️⃣ 异步上下文管理器")
    print("-" * 30)
    
    # 正常情况
    try:
        async with AsyncConnectionManager("正常连接") as conn:
            await conn.send_data("Hello World")
            await conn.send_data("异步编程很强大")
    except Exception as e:
        print(f"❌ 正常连接出错: {e}")
    
    # 异常情况
    try:
        async with AsyncConnectionManager("异常连接") as conn:
            await conn.send_data("第一条消息")
            raise ValueError("模拟异常")
            await conn.send_data("这条消息不会发送")
    except Exception as e:
        print(f"🔍 捕获异常: {e}")

# ===========================================
# 5. 异步生成器
# ===========================================

async def async_message_generator(messages: List[str]):
    """异步消息生成器"""
    for i, message in enumerate(messages):
        print(f"📨 生成消息 {i+1}: {message}")
        await asyncio.sleep(0.5)  # 模拟消息生成间隔
        yield {"id": i+1, "content": message, "timestamp": time.time()}

async def async_generator_demo():
    """异步生成器演示"""
    print("\n\n5️⃣ 异步生成器")
    print("-" * 30)
    
    messages = [
        "欢迎使用小智助手",
        "我正在为您处理请求",
        "处理完成，感谢使用"
    ]
    
    # 使用异步生成器
    async for message_data in async_message_generator(messages):
        print(f"📬 收到消息: {message_data}")
        # 模拟消息处理
        await asyncio.sleep(0.2)

# ===========================================
# 主函数
# ===========================================

async def main():
    """主异步函数"""
    print("🚀 开始异步编程演示")
    
    # 运行所有演示
    await basic_async_demo()
    await websocket_demo()
    await voice_demo()
    await async_context_demo()
    await async_generator_demo()
    
    print("\n" + "=" * 50)
    print("🎉 异步编程示例演示完成！")
    print("💡 关键要点:")
    print("   1. 使用 async/await 实现异步编程")
    print("   2. 使用 asyncio.gather() 并发执行任务")
    print("   3. 异步上下文管理器管理资源")
    print("   4. 异步生成器处理流式数据")
    print("   5. 在小智项目中，异步编程主要用于WebSocket通信和语音处理")

if __name__ == "__main__":
    # 运行主异步函数
    asyncio.run(main())