#!/usr/bin/env python3
"""
线程池使用示例
模拟小智项目中的线程池使用场景
"""

import time
import threading
from concurrent.futures import ThreadPoolExecutor
import uuid
import json

print("🧵 线程池使用示例")
print("=" * 50)

# ===========================================
# 1. 基础线程池使用
# ===========================================

def simple_task(name, duration):
    """简单的耗时任务"""
    print(f"任务 {name} 开始执行，预计耗时 {duration} 秒")
    time.sleep(duration)
    a = f"任务 {name} 完成！"
    print(f"✅ {a}")
    return a

print("\n1️⃣ 基础线程池使用")
print("-" * 30)

# 创建线程池
executor = ThreadPoolExecutor(max_workers=3)

# 提交任务
futures = []
for i in range(5):
    future = executor.submit(simple_task, f"任务{i+1}", i+1)
    futures.append(future)

# 等待所有任务完成
for future in futures:
    result = future.result()
    print(f"获取结果: {result}")

# 关闭线程池
executor.shutdown(wait=True)
print("✅ 所有任务完成")

# ===========================================
# 2. 模拟小智项目中的LLM调用
# ===========================================

class MockLLM:
    """模拟的LLM类"""
    def __init__(self, model_name):
        self.model_name = model_name
    
    def generate_response(self, prompt):
        """模拟LLM生成响应"""
        print(f"🤖 {self.model_name} 正在处理: {prompt[:20]}...")
        # 模拟LLM处理时间
        time.sleep(2)
        response = f"AI回复: 我理解了您的问题 '{prompt}'，这是我的回答。"
        print(f"✅ {self.model_name} 响应完成")
        return response

class MockConnection:
    """模拟的连接类"""
    def __init__(self, device_id):
        self.device_id = device_id
        self.session_id = str(uuid.uuid4())
        self.executor = ThreadPoolExecutor(max_workers=5)
        self.llm = MockLLM("ChatGPT-4")
        self.dialogue_history = []
        
    def chat(self, user_input):
        """聊天方法 - 在线程池中执行"""
        print(f"📱 设备 {self.device_id} 收到用户输入: {user_input}")
        
        # 将LLM调用放入线程池（避免阻塞主线程）
        def llm_process():
            try:
                # 模拟添加到对话历史
                self.dialogue_history.append({"role": "user", "content": user_input})
                
                # 调用LLM
                response = self.llm.generate_response(user_input)
                
                # 添加AI回复到历史
                self.dialogue_history.append({"role": "assistant", "content": response})
                
                print(f"📤 向设备 {self.device_id} 发送响应: {response}")
                return response
                
            except Exception as e:
                print(f"❌ LLM处理出错: {e}")
                return "抱歉，我遇到了一些问题。"
        
        # 提交到线程池
        future = self.executor.submit(llm_process)
        return future
    
    def cleanup(self):
        """清理资源"""
        if self.executor:
            self.executor.shutdown(wait=False)
            print(f"🧹 设备 {self.device_id} 连接已清理")

print("\n\n2️⃣ 模拟小智项目中的LLM调用")
print("-" * 30)

# 创建模拟连接
conn = MockConnection("ESP32_001")

# 模拟用户输入
user_inputs = [
    "你好，今天天气怎么样？",
    "请帮我设置一个提醒",
    "播放一首音乐"
]

# 并发处理多个用户输入
futures = []
for user_input in user_inputs:
    future = conn.chat(user_input)
    futures.append(future)

# 等待所有LLM调用完成
for future in futures:
    result = future.result()
    print(f"🎯 处理完成: {result[:30]}...")

# 清理连接
conn.cleanup()

# ===========================================
# 3. 模拟意图函数执行
# ===========================================

def mock_intent_function(conn, function_name, arguments):
    """模拟意图函数执行"""
    print(f"🎯 执行意图函数: {function_name}")
    print(f"📋 参数: {arguments}")
    
    # 模拟不同类型的函数执行时间
    if function_name == "get_weather":
        time.sleep(1)  # 模拟天气API调用
        return {"action": "RESPONSE", "result": "今天北京天气晴朗，温度20°C"}
    
    elif function_name == "play_music":
        time.sleep(2)  # 模拟音乐服务调用
        return {"action": "RESPONSE", "result": "正在播放音乐：《告白气球》"}
    
    elif function_name == "set_reminder":
        time.sleep(0.5)  # 模拟设置提醒
        return {"action": "RESPONSE", "result": "提醒已设置成功"}
    
    else:
        return {"action": "ERROR", "result": "未知的意图函数"}

class MockIntentHandler:
    """模拟意图处理器"""
    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=5)
    
    def process_intent(self, conn, intent_data):
        """处理意图 - 在线程池中执行"""
        function_name = intent_data.get("function_name")
        arguments = intent_data.get("arguments", {})
        
        print(f"🧠 开始处理意图: {function_name}")
        
        def intent_executor():
            try:
                result = mock_intent_function(conn, function_name, arguments)
                print(f"✅ 意图处理完成: {function_name}")
                return result
            except Exception as e:
                print(f"❌ 意图处理出错: {e}")
                return {"action": "ERROR", "result": str(e)}
        
        # 提交到线程池
        future = self.executor.submit(intent_executor)
        return future
    
    def cleanup(self):
        """清理资源"""
        if self.executor:
            self.executor.shutdown(wait=False)

print("\n\n3️⃣ 模拟意图函数执行")
print("-" * 30)

# 创建意图处理器
intent_handler = MockIntentHandler()

# 模拟意图数据
intents = [
    {"function_name": "get_weather", "arguments": {"location": "北京"}},
    {"function_name": "play_music", "arguments": {"song": "告白气球"}},
    {"function_name": "set_reminder", "arguments": {"time": "18:00", "message": "下班"}},
]

# 并发处理多个意图
futures = []
for intent in intents:
    future = intent_handler.process_intent(conn, intent)
    futures.append(future)

# 等待所有意图处理完成
for future in futures:
    result = future.result()
    print(f"🎯 意图结果: {result}")

# 清理资源
intent_handler.cleanup()

# ===========================================
# 4. 线程池最佳实践
# ===========================================

print("\n\n4️⃣ 线程池最佳实践")
print("-" * 30)

class BestPracticeExample:
    """线程池最佳实践示例"""
    
    def __init__(self, max_workers=5):
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.shutdown_flag = False
    
    def submit_task(self, func, *args, **kwargs):
        """提交任务的安全方法"""
        if self.shutdown_flag:
            print("❌ 线程池已关闭，无法提交新任务")
            return None
        
        try:
            future = self.executor.submit(func, *args, **kwargs)
            return future
        except Exception as e:
            print(f"❌ 提交任务失败: {e}")
            return None
    
    def safe_shutdown(self, wait=True):
        """安全关闭线程池"""
        print("🔄 开始关闭线程池...")
        self.shutdown_flag = True
        
        try:
            self.executor.shutdown(wait=wait)
            print("✅ 线程池已安全关闭")
        except Exception as e:
            print(f"❌ 关闭线程池时出错: {e}")
    
    def get_thread_status(self):
        """获取线程池状态"""
        return {
            "shutdown": self.shutdown_flag,
            "executor_shutdown": self.executor._shutdown
        }

# 创建最佳实践示例
bp_example = BestPracticeExample(max_workers=3)

# 提交一些任务
def sample_work(work_id):
    print(f"🔧 执行工作 {work_id}")
    time.sleep(1)
    return f"工作 {work_id} 完成"

# 提交任务
futures = []
for i in range(3):
    future = bp_example.submit_task(sample_work, i+1)
    if future:
        futures.append(future)

# 等待结果
for future in futures:
    result = future.result()
    print(f"📋 结果: {result}")

# 检查状态
print(f"📊 线程池状态: {bp_example.get_thread_status()}")

# 安全关闭
bp_example.safe_shutdown()

print("\n" + "=" * 50)
print("🎉 线程池示例演示完成！")
print("💡 关键要点:")
print("   1. 使用线程池避免频繁创建销毁线程")
print("   2. 合理设置max_workers数量")
print("   3. 及时关闭线程池释放资源")
print("   4. 异常处理保证程序稳定性")
print("   5. 在小智项目中，线程池主要用于LLM调用和意图函数执行")