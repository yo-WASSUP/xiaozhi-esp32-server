"""
SenseVoice 热词功能技术验证脚本

测试 FunASR SenseVoiceSmall 的 hotword_list 参数是否对识别结果有实际影响。
对比有热词和无热词两种情况下的识别结果。
"""

import time
from funasr import AutoModel
from funasr.utils.postprocess_utils import rich_transcription_postprocess

MODEL_DIR = "models/SenseVoiceSmall"
TEST_AUDIO = f"{MODEL_DIR}/example/zh.mp3"

# === 自定义热词列表 ===
# 在这里填入你想要优化识别的专有名词、人名等
HOTWORD_LIST = ["小智", "张三", "李四", "量子计算", "区块链"]


def run_asr(model, audio_path, label=""):
    """运行一次 ASR 并返回结果和耗时"""
    start = time.time()
    result = model.generate(
        input=audio_path,
        cache={},
        language="auto",
        use_itn=True,
        batch_size_s=60,
    )
    elapsed = time.time() - start
    text = rich_transcription_postprocess(result[0]["text"])
    print(f"[{label}] 耗时: {elapsed:.3f}s")
    print(f"[{label}] 原始输出: {result[0]['text']}")
    print(f"[{label}] 处理后文本: {text}")
    print()
    return text, elapsed


def main():
    print("=" * 60)
    print("SenseVoice 热词功能验证")
    print("=" * 60)
    print(f"模型: {MODEL_DIR}")
    print(f"测试音频: {TEST_AUDIO}")
    print(f"热词列表: {HOTWORD_LIST}")
    print()

    # --- 测试 1: 不带热词 ---
    print("-" * 40)
    print("测试 1: 基准识别（无热词）")
    print("-" * 40)
    model_base = AutoModel(
        model=MODEL_DIR,
        disable_update=True,
        hub="hf",
    )
    text_base, time_base = run_asr(model_base, TEST_AUDIO, "无热词")

    # --- 测试 2: 带热词，权重 1.5 ---
    print("-" * 40)
    print("测试 2: 热词识别（weight=1.5）")
    print("-" * 40)
    try:
        model_hw15 = AutoModel(
            model=MODEL_DIR,
            hotword_list=HOTWORD_LIST,
            hotword_weight=1.5,
            disable_update=True,
            hub="hf",
        )
        text_hw15, time_hw15 = run_asr(model_hw15, TEST_AUDIO, "热词w=1.5")
    except Exception as e:
        print(f"[热词w=1.5] 加载失败: {e}")
        text_hw15, time_hw15 = None, None

    # --- 测试 3: 带热词，权重 2.0 ---
    print("-" * 40)
    print("测试 3: 热词识别（weight=2.0）")
    print("-" * 40)
    try:
        model_hw20 = AutoModel(
            model=MODEL_DIR,
            hotword_list=HOTWORD_LIST,
            hotword_weight=2.0,
            disable_update=True,
            hub="hf",
        )
        text_hw20, time_hw20 = run_asr(model_hw20, TEST_AUDIO, "热词w=2.0")
    except Exception as e:
        print(f"[热词w=2.0] 加载失败: {e}")
        text_hw20, time_hw20 = None, None

    # --- 测试 4: 热词通过 generate 参数传入 ---
    print("-" * 40)
    print("测试 4: 通过 generate() 参数传入热词")
    print("-" * 40)
    try:
        start = time.time()
        result = model_base.generate(
            input=TEST_AUDIO,
            cache={},
            language="auto",
            use_itn=True,
            batch_size_s=60,
            hotword=" ".join(HOTWORD_LIST),
        )
        elapsed = time.time() - start
        text_gen = rich_transcription_postprocess(result[0]["text"])
        print(f"[generate热词] 耗时: {elapsed:.3f}s")
        print(f"[generate热词] 原始输出: {result[0]['text']}")
        print(f"[generate热词] 处理后文本: {text_gen}")
        print()
    except Exception as e:
        print(f"[generate热词] 失败: {e}")
        text_gen = None

    # --- 结果对比 ---
    print("=" * 60)
    print("结果对比")
    print("=" * 60)
    print(f"基准结果:       {text_base}")
    if text_hw15:
        print(f"热词(w=1.5):    {text_hw15}")
        print(f"  与基准相同: {'是' if text_hw15 == text_base else '否'}")
    if text_hw20:
        print(f"热词(w=2.0):    {text_hw20}")
        print(f"  与基准相同: {'是' if text_hw20 == text_base else '否'}")
    if text_gen:
        print(f"generate热词:   {text_gen}")
        print(f"  与基准相同: {'是' if text_gen == text_base else '否'}")

    print()
    print("耗时对比:")
    print(f"  基准:         {time_base:.3f}s")
    if time_hw15:
        print(f"  热词(w=1.5):  {time_hw15:.3f}s (差异: {time_hw15 - time_base:+.3f}s)")
    if time_hw20:
        print(f"  热词(w=2.0):  {time_hw20:.3f}s (差异: {time_hw20 - time_base:+.3f}s)")


if __name__ == "__main__":
    main()
