#!/usr/bin/env python3
"""
队列缓冲机制使用示例
模拟小智项目中的队列使用场景
"""

import queue
import threading
import time
import json
import uuid
from typing import List, Dict, Any
from enum import Enum
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor

print("📦 队列缓冲机制使用示例")
print("=" * 50)

# ===========================================
# 1. 基础队列使用
# ===========================================

def basic_queue_demo():
    """基础队列演示"""
    print("\n1️⃣ 基础队列使用")
    print("-" * 30)
    
    # 创建队列
    q = queue.Queue(maxsize=5)  # 最大容量5
    
    # 生产者函数
    def producer(name: str, items: List[str]):
        for item in items:
            print(f"📥 生产者 {name} 放入: {item}")
            q.put(item)
            time.sleep(0.5)
        print(f"✅ 生产者 {name} 完成")
    
    # 消费者函数
    def consumer(name: str, count: int):
        for _ in range(count):
            try:
                item = q.get(timeout=2)  # 2秒超时
                print(f"📤 消费者 {name} 取出: {item}")
                q.task_done()  # 标记任务完成
                time.sleep(0.3)
            except queue.Empty:
                print(f"⏰ 消费者 {name} 超时")
                break
        print(f"✅ 消费者 {name} 完成")
    
    # 创建生产者和消费者线程
    producer_thread = threading.Thread(
        target=producer, 
        args=("生产者1", ["苹果", "香蕉", "橙子", "葡萄"])
    )
    consumer_thread = threading.Thread(
        target=consumer, 
        args=("消费者1", 4)
    )
    
    # 启动线程
    producer_thread.start()
    consumer_thread.start()
    
    # 等待线程完成
    producer_thread.join()
    consumer_thread.join()
    
    # 等待队列中所有任务完成
    q.join()
    print("📋 队列处理完成")

# ===========================================
# 2. 模拟音频数据队列
# ===========================================

@dataclass
class AudioData:
    """音频数据类"""
    timestamp: float
    data: bytes
    duration: float
    has_voice: bool

class AudioProcessor:
    """音频处理器"""
    def __init__(self):
        self.audio_queue = queue.Queue()
        self.is_processing = False
        self.processor_thread = None
    
    def start_processing(self):
        """启动音频处理线程"""
        if not self.is_processing:
            self.is_processing = True
            self.processor_thread = threading.Thread(target=self._process_audio)
            self.processor_thread.start()
            print("🎤 音频处理器已启动")
    
    def stop_processing(self):
        """停止音频处理"""
        if self.is_processing:
            self.is_processing = False
            # 放入停止信号
            self.audio_queue.put(None)
            if self.processor_thread:
                self.processor_thread.join()
            print("🛑 音频处理器已停止")
    
    def add_audio(self, audio_data: AudioData):
        """添加音频数据到队列"""
        self.audio_queue.put(audio_data)
        print(f"📥 音频数据入队: {audio_data.duration}s, 有语音: {audio_data.has_voice}")
    
    def _process_audio(self):
        """处理音频数据"""
        audio_buffer = []
        
        while self.is_processing:
            try:
                audio_data = self.audio_queue.get(timeout=1)
                
                # 检查停止信号
                if audio_data is None:
                    break
                
                # 处理音频数据
                if audio_data.has_voice:
                    audio_buffer.append(audio_data)
                    print(f"🎙️ 检测到语音，缓冲区大小: {len(audio_buffer)}")
                else:
                    if audio_buffer:
                        # 处理缓冲区中的语音
                        await self._process_voice_buffer(audio_buffer)
                        audio_buffer.clear()
                    else:
                        print("🔇 静音片段，跳过")
                
                self.audio_queue.task_done()
                
            except queue.Empty:
                # 超时检查缓冲区
                if audio_buffer:
                    print("⏰ 处理超时，强制处理缓冲区")
                    await self._process_voice_buffer(audio_buffer)
                    audio_buffer.clear()
                continue
        
        # 处理剩余的缓冲区
        if audio_buffer:
            await self._process_voice_buffer(audio_buffer)
    
    async def _process_voice_buffer(self, audio_buffer: List[AudioData]):
        """处理语音缓冲区"""
        total_duration = sum(audio.duration for audio in audio_buffer)
        print(f"🗣️ 处理语音缓冲区: {len(audio_buffer)} 个片段, 总时长: {total_duration:.2f}s")
        
        # 模拟语音识别处理时间
        time.sleep(0.5)
        
        # 模拟识别结果
        results = ["你好小智", "播放音乐", "查询天气", "设置提醒"]
        import random
        result = random.choice(results)
        print(f"📝 语音识别结果: {result}")
        return result

def audio_queue_demo():
    """音频队列演示"""
    print("\n\n2️⃣ 模拟音频数据队列")
    print("-" * 30)
    
    # 创建音频处理器
    processor = AudioProcessor()
    processor.start_processing()
    
    # 模拟音频数据流
    audio_samples = [
        AudioData(time.time(), b"audio_data_1", 0.5, False),  # 静音
        AudioData(time.time(), b"audio_data_2", 0.5, True),   # 语音开始
        AudioData(time.time(), b"audio_data_3", 0.5, True),   # 语音持续
        AudioData(time.time(), b"audio_data_4", 0.5, True),   # 语音持续
        AudioData(time.time(), b"audio_data_5", 0.5, False),  # 语音结束
        AudioData(time.time(), b"audio_data_6", 0.5, False),  # 静音
    ]
    
    # 模拟音频数据输入
    for audio in audio_samples:
        processor.add_audio(audio)
        time.sleep(0.2)  # 模拟音频流间隔
    
    # 等待处理完成
    time.sleep(2)
    
    # 停止处理器
    processor.stop_processing()

# ===========================================
# 3. 模拟TTS文本和音频队列
# ===========================================

class SentenceType(Enum):
    """句子类型"""
    FIRST = "first"
    MIDDLE = "middle"
    LAST = "last"

class ContentType(Enum):
    """内容类型"""
    TEXT = "text"
    ACTION = "action"

@dataclass
class TTSTextMessage:
    """TTS文本消息"""
    sentence_id: str
    sentence_type: SentenceType
    content_type: ContentType
    content: str = ""

@dataclass
class TTSAudioMessage:
    """TTS音频消息"""
    sentence_type: SentenceType
    audio_data: bytes
    text: str

class TTSEngine:
    """TTS引擎"""
    def __init__(self):
        self.text_queue = queue.Queue()
        self.audio_queue = queue.Queue()
        self.is_running = False
        self.text_processor = None
        self.audio_processor = None
    
    def start(self):
        """启动TTS引擎"""
        if not self.is_running:
            self.is_running = True
            self.text_processor = threading.Thread(target=self._process_text)
            self.audio_processor = threading.Thread(target=self._process_audio)
            self.text_processor.start()
            self.audio_processor.start()
            print("🔊 TTS引擎已启动")
    
    def stop(self):
        """停止TTS引擎"""
        if self.is_running:
            self.is_running = False
            # 放入停止信号
            self.text_queue.put(None)
            self.audio_queue.put(None)
            
            if self.text_processor:
                self.text_processor.join()
            if self.audio_processor:
                self.audio_processor.join()
            print("🛑 TTS引擎已停止")
    
    def add_text(self, message: TTSTextMessage):
        """添加文本到队列"""
        self.text_queue.put(message)
        print(f"📝 文本入队: {message.content}")
    
    def add_audio(self, message: TTSAudioMessage):
        """添加音频到队列"""
        self.audio_queue.put(message)
        print(f"🎵 音频入队: {message.text}")
    
    def _process_text(self):
        """处理文本队列"""
        while self.is_running:
            try:
                message = self.text_queue.get(timeout=1)
                
                if message is None:
                    break
                
                # 模拟文本处理
                print(f"📖 处理文本: {message.content}")
                
                if message.content:
                    # 模拟TTS合成
                    time.sleep(0.3)  # 模拟合成时间
                    
                    # 生成音频数据
                    audio_data = f"<audio_for:{message.content}>".encode()
                    audio_message = TTSAudioMessage(
                        sentence_type=message.sentence_type,
                        audio_data=audio_data,
                        text=message.content
                    )
                    
                    # 放入音频队列
                    self.add_audio(audio_message)
                
                self.text_queue.task_done()
                
            except queue.Empty:
                continue
    
    def _process_audio(self):
        """处理音频队列"""
        while self.is_running:
            try:
                message = self.audio_queue.get(timeout=1)
                
                if message is None:
                    break
                
                # 模拟音频播放
                print(f"🔊 播放音频: {message.text} (类型: {message.sentence_type.value})")
                time.sleep(0.5)  # 模拟播放时间
                
                self.audio_queue.task_done()
                
            except queue.Empty:
                continue

def tts_queue_demo():
    """TTS队列演示"""
    print("\n\n3️⃣ 模拟TTS文本和音频队列")
    print("-" * 30)
    
    # 创建TTS引擎
    tts = TTSEngine()
    tts.start()
    
    # 模拟对话
    conversation = [
        "你好，我是小智助手",
        "很高兴为您服务",
        "请问有什么可以帮助您的吗？"
    ]
    
    sentence_id = str(uuid.uuid4())
    
    # 添加文本消息
    for i, text in enumerate(conversation):
        if i == 0:
            sentence_type = SentenceType.FIRST
        elif i == len(conversation) - 1:
            sentence_type = SentenceType.LAST
        else:
            sentence_type = SentenceType.MIDDLE
        
        message = TTSTextMessage(
            sentence_id=sentence_id,
            sentence_type=sentence_type,
            content_type=ContentType.TEXT,
            content=text
        )
        
        tts.add_text(message)
        time.sleep(0.1)
    
    # 等待处理完成
    time.sleep(3)
    
    # 停止TTS引擎
    tts.stop()

# ===========================================
# 4. 模拟上报队列
# ===========================================

@dataclass
class ReportData:
    """上报数据"""
    device_id: str
    event_type: str
    data: Dict[str, Any]
    timestamp: float

class ReportManager:
    """上报管理器"""
    def __init__(self):
        self.report_queue = queue.Queue()
        self.is_running = False
        self.report_thread = None
        self.batch_size = 3
        self.batch_timeout = 2.0
    
    def start(self):
        """启动上报管理器"""
        if not self.is_running:
            self.is_running = True
            self.report_thread = threading.Thread(target=self._process_reports)
            self.report_thread.start()
            print("📊 上报管理器已启动")
    
    def stop(self):
        """停止上报管理器"""
        if self.is_running:
            self.is_running = False
            self.report_queue.put(None)
            if self.report_thread:
                self.report_thread.join()
            print("🛑 上报管理器已停止")
    
    def add_report(self, report: ReportData):
        """添加上报数据"""
        self.report_queue.put(report)
        print(f"📈 上报数据入队: {report.event_type} from {report.device_id}")
    
    def _process_reports(self):
        """处理上报数据"""
        batch = []
        last_process_time = time.time()
        
        while self.is_running:
            try:
                report = self.report_queue.get(timeout=0.5)
                
                if report is None:
                    break
                
                batch.append(report)
                current_time = time.time()
                
                # 批量处理条件：达到批次大小或超时
                if (len(batch) >= self.batch_size or 
                    current_time - last_process_time >= self.batch_timeout):
                    
                    self._send_batch(batch)
                    batch.clear()
                    last_process_time = current_time
                
                self.report_queue.task_done()
                
            except queue.Empty:
                # 超时检查是否需要发送剩余批次
                if batch and time.time() - last_process_time >= self.batch_timeout:
                    self._send_batch(batch)
                    batch.clear()
                    last_process_time = time.time()
                continue
        
        # 发送剩余的批次
        if batch:
            self._send_batch(batch)
    
    def _send_batch(self, batch: List[ReportData]):
        """发送批次数据"""
        print(f"📤 发送批次上报: {len(batch)} 条记录")
        
        for report in batch:
            print(f"   - {report.event_type}: {report.device_id}")
        
        # 模拟网络发送
        time.sleep(0.2)
        print("✅ 批次上报成功")

def report_queue_demo():
    """上报队列演示"""
    print("\n\n4️⃣ 模拟上报队列")
    print("-" * 30)
    
    # 创建上报管理器
    report_manager = ReportManager()
    report_manager.start()
    
    # 模拟不同类型的上报数据
    reports = [
        ReportData("ESP32_001", "voice_start", {"duration": 0}, time.time()),
        ReportData("ESP32_002", "tts_start", {"text": "hello"}, time.time()),
        ReportData("ESP32_001", "voice_end", {"duration": 3.5}, time.time()),
        ReportData("ESP32_003", "voice_start", {"duration": 0}, time.time()),
        ReportData("ESP32_002", "tts_end", {"success": True}, time.time()),
        ReportData("ESP32_003", "voice_end", {"duration": 2.1}, time.time()),
    ]
    
    # 添加上报数据
    for report in reports:
        report_manager.add_report(report)
        time.sleep(0.3)  # 模拟事件间隔
    
    # 等待处理完成
    time.sleep(3)
    
    # 停止上报管理器
    report_manager.stop()

# ===========================================
# 5. 优先级队列示例
# ===========================================

@dataclass
class PriorityTask:
    """优先级任务"""
    priority: int
    task_id: str
    content: str
    
    def __lt__(self, other):
        # 数字越小优先级越高
        return self.priority < other.priority

def priority_queue_demo():
    """优先级队列演示"""
    print("\n\n5️⃣ 优先级队列示例")
    print("-" * 30)
    
    # 创建优先级队列
    pq = queue.PriorityQueue()
    
    # 添加不同优先级的任务
    tasks = [
        PriorityTask(3, "task_1", "普通任务1"),
        PriorityTask(1, "task_2", "紧急任务"),
        PriorityTask(2, "task_3", "重要任务"),
        PriorityTask(3, "task_4", "普通任务2"),
        PriorityTask(1, "task_5", "另一个紧急任务"),
    ]
    
    print("📥 添加任务:")
    for task in tasks:
        pq.put(task)
        print(f"   - {task.task_id}: {task.content} (优先级: {task.priority})")
    
    print("\n📤 按优先级处理任务:")
    while not pq.empty():
        task = pq.get()
        print(f"   - 处理 {task.task_id}: {task.content} (优先级: {task.priority})")
        time.sleep(0.1)

# ===========================================
# 主函数
# ===========================================

def main():
    """主函数"""
    print("🚀 开始队列缓冲机制演示")
    
    # 运行所有演示
    basic_queue_demo()
    audio_queue_demo()
    tts_queue_demo()
    report_queue_demo()
    priority_queue_demo()
    
    print("\n" + "=" * 50)
    print("🎉 队列缓冲机制示例演示完成！")
    print("💡 关键要点:")
    print("   1. 使用队列实现生产者-消费者模式")
    print("   2. 队列提供线程安全的数据交换")
    print("   3. 不同类型的队列适用于不同场景")
    print("   4. 合理设置队列大小避免内存溢出")
    print("   5. 在小智项目中，队列主要用于音频缓冲、TTS处理和数据上报")

if __name__ == "__main__":
    main()