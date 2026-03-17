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

# 添加 Fun-ASR 目录到 path，以便 funasr 加载 remote_code (model.py)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "Fun-ASR"))

# === 配置 ===
MODEL_DIR = "FunAudioLLM/Fun-ASR-Nano-2512"
AUDIO_DIR = os.path.join(os.path.dirname(__file__), "audio")
AUDIO_EXTS = {".wav", ".mp3", ".flac", ".m4a"}

# === 自定义热词列表 ===
HOTWORD_LIST = [
    # --- 容易混淆的两字人名 ---
    "张玮",       # zhāng wěi / wēi / wěi
    # --- 容易混淆的三字人名 ---
    "王小明",  # wáng/wāng xiǎo míng
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


def find_audio_files():
    """扫描 audio/ 目录下的音频文件"""
    if not os.path.isdir(AUDIO_DIR):
        os.makedirs(AUDIO_DIR)
        return []
    files = sorted(
        f for f in os.listdir(AUDIO_DIR)
        if os.path.splitext(f)[1].lower() in AUDIO_EXTS
    )
    return [os.path.join(AUDIO_DIR, f) for f in files]


def main():
    print("=" * 60)
    print("Fun-ASR-Nano-2512 热词功能验证")
    print("=" * 60)
    print(f"模型: {MODEL_DIR}")
    print(f"音频目录: {AUDIO_DIR}")
    print(f"热词列表: {HOTWORD_LIST}")
    print()

    audio_files = find_audio_files()
    if not audio_files:
        print(f"错误：audio/ 目录下没有音频文件")
        print(f"请将测试音频放入: {AUDIO_DIR}")
        print(f"支持格式: {', '.join(AUDIO_EXTS)}")
        return

    print(f"找到 {len(audio_files)} 个音频文件:")
    for f in audio_files:
        print(f"  - {os.path.basename(f)}")
    print()

    device = get_device()
    model = load_model(device)

    for i, audio_path in enumerate(audio_files, 1):
        name = os.path.basename(audio_path)
        print("=" * 60)
        print(f"音频 {i}/{len(audio_files)}: {name}")
        print("=" * 60)

        # 无热词（基准）
        print("-" * 40)
        print("基准识别（无热词）")
        print("-" * 40)
        text_base, time_base = run_asr(model, audio_path, label="无热词")

        # 有热词
        print("-" * 40)
        print("热词识别")
        print("-" * 40)
        text_hw, time_hw = run_asr(model, audio_path, hotwords=HOTWORD_LIST, label="有热词")

        # 对比
        print("-" * 40)
        print("对比结果")
        print("-" * 40)
        print(f"  无热词: {text_base}")
        print(f"  有热词: {text_hw}")
        print(f"  结果相同: {'是' if text_hw == text_base else '否 ← 热词生效！'}")
        print(f"  耗时差异: {time_hw - time_base:+.3f}s")
        print()


if __name__ == "__main__":
    main()
