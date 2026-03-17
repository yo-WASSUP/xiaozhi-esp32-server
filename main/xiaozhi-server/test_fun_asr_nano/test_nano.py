"""
Fun-ASR-Nano-2512 热词功能测试脚本

测试内容：
1. 基础语音识别能力
2. 热词（hotword）功能 —— 对比不同热词权重对识别结果的影响

使用前：
  pip install -r requirements.txt
  # 或手动安装：pip install funasr torch torchaudio
  # 模型会在首次运行时自动从 HuggingFace 下载（约 3.2GB）
"""

import os
import sys
import time
import torch

# 添加父目录到 path，以便复用项目中的模型
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# === 配置 ===
MODEL_DIR = "FunAudioLLM/Fun-ASR-Nano-2512"
TEST_AUDIO = os.path.join(os.path.dirname(__file__), "..", "models", "SenseVoiceSmall", "example", "chafang.mp3")
# 音频内容：各位注意，现在开始查房。我是黎建国，赵雨萱昨晚有点发烧，请核实一下。
# 十二号床王晓明的CT结果出来了吗？张志远家属问手术方案的事，跟他说张玮教授下午会过来跟他们谈。

# === 自定义热词列表 ===
HOTWORD_LIST = [
    # --- 容易混淆的两字人名 ---
    "张玮",       # zhāng wěi / wēi / wěi
    # --- 容易混淆的三字人名 ---
    "王晓明",  # wáng/wāng xiǎo míng
    "黎建国",  # lǐ/lí jiàn guó
    "赵雨萱",   # zhào yǔ xuān
    "张致远",  # zhāng zhì yuǎn
]


def get_device():
    """自动检测可用设备"""
    if torch.cuda.is_available():
        device = "cuda:0"
        print(f"使用 GPU: {torch.cuda.get_device_name(0)}")
    elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        device = "mps"
        print("使用 Apple MPS 加速")
    else:
        device = "cpu"
        print("使用 CPU（推理会较慢）")
    return device


def load_model(device):
    """加载 Fun-ASR-Nano 模型"""
    from funasr import AutoModel

    print(f"加载模型: {MODEL_DIR} ...")
    load_start = time.time()
    model = AutoModel(
        model=MODEL_DIR,
        trust_remote_code=True,
        remote_code="./model.py",
        device=device,
        hub="hf",
    )
    print(f"模型加载耗时: {time.time() - load_start:.1f}s")
    return model


def run_asr(model, audio_path, hotwords=None, label=""):
    """运行一次 ASR 并返回结果和耗时"""
    kwargs = dict(
        input=[audio_path],
        cache={},
        batch_size=1,
        language="中文",
        itn=True,
    )
    if hotwords is not None:
        kwargs["hotwords"] = hotwords

    start = time.time()
    result = model.generate(**kwargs)
    elapsed = time.time() - start
    text = result[0]["text"]
    print(f"[{label}] 耗时: {elapsed:.3f}s")
    print(f"[{label}] 结果: {text}")
    print()
    return text, elapsed


def main():
    print("=" * 60)
    print("Fun-ASR-Nano-2512 热词功能验证")
    print("=" * 60)
    print(f"模型: {MODEL_DIR}")
    print(f"测试音频: {TEST_AUDIO}")
    print(f"热词列表: {HOTWORD_LIST}")
    print()

    if not os.path.exists(TEST_AUDIO):
        print(f"错误：测试音频不存在: {TEST_AUDIO}")
        return

    device = get_device()
    model = load_model(device)

    # --- 测试 1: 不带热词（基准） ---
    print("-" * 40)
    print("测试 1: 基准识别（无热词）")
    print("-" * 40)
    text_base, time_base = run_asr(model, TEST_AUDIO, label="无热词")

    # --- 测试 2: 带热词，默认权重 ---
    print("-" * 40)
    print("测试 2: 热词识别（默认权重）")
    print("-" * 40)
    text_hw, time_hw = run_asr(model, TEST_AUDIO, hotwords=HOTWORD_LIST, label="热词-默认")

    # --- 测试 3: 带热词，用字符串形式传入 ---
    print("-" * 40)
    print("测试 3: 热词识别（字符串形式）")
    print("-" * 40)
    hotwords_str = " ".join(HOTWORD_LIST)
    text_hw_str, time_hw_str = run_asr(model, TEST_AUDIO, hotwords=hotwords_str, label="热词-字符串")

    # --- 结果对比 ---
    print("=" * 60)
    print("结果对比")
    print("=" * 60)
    print(f"基准结果:       {text_base}")
    print(f"热词(列表):     {text_hw}")
    print(f"  与基准相同: {'是' if text_hw == text_base else '否 ← 热词生效！'}")
    print(f"热词(字符串):   {text_hw_str}")
    print(f"  与基准相同: {'是' if text_hw_str == text_base else '否 ← 热词生效！'}")

    print()
    print("耗时对比:")
    print(f"  基准:         {time_base:.3f}s")
    print(f"  热词(列表):   {time_hw:.3f}s (差异: {time_hw - time_base:+.3f}s)")
    print(f"  热词(字符串): {time_hw_str:.3f}s (差异: {time_hw_str - time_base:+.3f}s)")


if __name__ == "__main__":
    main()
