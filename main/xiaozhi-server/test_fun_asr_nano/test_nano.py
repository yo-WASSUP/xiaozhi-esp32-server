"""
Fun-ASR-Nano-2512 能力测试脚本

测试内容：
1. 基础语音识别能力（中文、英文）
2. 热词（hotword）功能 —— 专有名词/人名识别增强
3. 与 SenseVoiceSmall 的对比（如果可用）
4. 推理速度

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


def test_nano_basic(device):
    """测试 1: Fun-ASR-Nano 基础识别能力"""
    from funasr import AutoModel

    print("\n" + "=" * 60)
    print("测试 1: Fun-ASR-Nano-2512 基础识别")
    print("=" * 60)

    model_dir = "FunAudioLLM/Fun-ASR-Nano-2512"
    print(f"加载模型: {model_dir} ...")

    load_start = time.time()
    model = AutoModel(
        model=model_dir,
        trust_remote_code=True,
        remote_code="./model.py",
        device=device,
        hub="hf",
    )
    print(f"模型加载耗时: {time.time() - load_start:.1f}s")

    # 用模型自带的示例音频测试
    zh_audio = f"{model.model_path}/example/zh.mp3"
    if os.path.exists(zh_audio):
        print(f"\n--- 中文识别 ({zh_audio}) ---")
        start = time.time()
        res = model.generate(
            input=[zh_audio],
            cache={},
            batch_size=1,
            language="中文",
            itn=True,
        )
        elapsed = time.time() - start
        print(f"结果: {res[0]['text']}")
        print(f"耗时: {elapsed:.3f}s")
    else:
        print(f"未找到示例音频: {zh_audio}")

    return model


def test_nano_hotword(model, device):
    """测试 2: 热词功能 —— 对比有无热词的识别差异"""
    print("\n" + "=" * 60)
    print("测试 2: 热词（Hotword）功能验证")
    print("=" * 60)

    zh_audio = f"{model.model_path}/example/zh.mp3"
    if not os.path.exists(zh_audio):
        print("跳过：没有测试音频")
        return

    # 不带热词
    print("\n--- 无热词 ---")
    start = time.time()
    res_base = model.generate(
        input=[zh_audio],
        cache={},
        batch_size=1,
        language="中文",
        itn=True,
    )
    time_base = time.time() - start
    text_base = res_base[0]["text"]
    print(f"结果: {text_base}")
    print(f"耗时: {time_base:.3f}s")

    # 带热词 —— 修改这里的热词列表来测试你的专有名词
    hotwords_list = ["小智", "张三", "李四", "量子计算", "区块链", "开放时间"]

    print(f"\n--- 有热词: {hotwords_list} ---")
    start = time.time()
    res_hw = model.generate(
        input=[zh_audio],
        cache={},
        batch_size=1,
        hotwords=hotwords_list,
        language="中文",
        itn=True,
    )
    time_hw = time.time() - start
    text_hw = res_hw[0]["text"]
    print(f"结果: {text_hw}")
    print(f"耗时: {time_hw:.3f}s")

    # 对比
    print(f"\n--- 对比 ---")
    print(f"无热词: {text_base}")
    print(f"有热词: {text_hw}")
    print(f"结果相同: {'是' if text_base == text_hw else '否 ← 热词生效！'}")
    print(f"耗时差异: {time_hw - time_base:+.3f}s")


def test_nano_custom_audio(model):
    """测试 3: 用自定义音频测试（如果有的话）"""
    print("\n" + "=" * 60)
    print("测试 3: 自定义音频测试")
    print("=" * 60)

    custom_dir = os.path.join(os.path.dirname(__file__), "audio")
    if not os.path.exists(custom_dir):
        os.makedirs(custom_dir, exist_ok=True)
        print(f"请将测试音频放入: {custom_dir}/")
        print("支持格式: .wav, .mp3, .flac, .m4a")
        print("跳过此测试。")
        return

    audio_files = [
        f for f in os.listdir(custom_dir)
        if f.endswith((".wav", ".mp3", ".flac", ".m4a"))
    ]

    if not audio_files:
        print(f"目录 {custom_dir}/ 中没有音频文件，跳过。")
        return

    # 你可以在这里自定义热词
    hotwords = ["小智", "张三", "李四"]
    print(f"热词列表: {hotwords}")

    for audio_file in audio_files:
        audio_path = os.path.join(custom_dir, audio_file)
        print(f"\n--- {audio_file} ---")

        # 无热词
        res_base = model.generate(
            input=[audio_path], cache={}, batch_size=1,
            language="中文", itn=True,
        )
        text_base = res_base[0]["text"]

        # 有热词
        res_hw = model.generate(
            input=[audio_path], cache={}, batch_size=1,
            hotwords=hotwords, language="中文", itn=True,
        )
        text_hw = res_hw[0]["text"]

        print(f"  无热词: {text_base}")
        print(f"  有热词: {text_hw}")
        if text_base != text_hw:
            print(f"  *** 热词生效！结果有变化 ***")


def test_compare_sensevoice(device):
    """测试 4: 与 SenseVoiceSmall 对比（可选）"""
    print("\n" + "=" * 60)
    print("测试 4: 与 SenseVoiceSmall 对比")
    print("=" * 60)

    sensevoice_dir = os.path.join(os.path.dirname(__file__), "..", "models", "SenseVoiceSmall")
    if not os.path.exists(sensevoice_dir):
        print(f"未找到 SenseVoiceSmall 模型: {sensevoice_dir}")
        print("跳过对比测试。")
        return

    from funasr import AutoModel

    print("加载 SenseVoiceSmall ...")
    model_sv = AutoModel(
        model=sensevoice_dir,
        disable_update=True,
        hub="hf",
    )

    # 使用 SenseVoice 自带示例
    zh_audio = os.path.join(sensevoice_dir, "example", "zh.mp3")
    if not os.path.exists(zh_audio):
        print("未找到 SenseVoice 示例音频，跳过。")
        return

    print(f"\n测试音频: {zh_audio}")

    # SenseVoiceSmall
    start = time.time()
    res_sv = model_sv.generate(
        input=zh_audio, cache={}, language="auto", use_itn=True, batch_size_s=60,
    )
    time_sv = time.time() - start
    from funasr.utils.postprocess_utils import rich_transcription_postprocess
    text_sv = rich_transcription_postprocess(res_sv[0]["text"])

    print(f"SenseVoiceSmall: {text_sv}")
    print(f"  耗时: {time_sv:.3f}s")

    # Fun-ASR-Nano
    print("\n加载 Fun-ASR-Nano ...")
    model_nano = AutoModel(
        model="FunAudioLLM/Fun-ASR-Nano-2512",
        trust_remote_code=True,
        remote_code="./model.py",
        device=device,
        hub="hf",
    )

    start = time.time()
    res_nano = model_nano.generate(
        input=[zh_audio], cache={}, batch_size=1,
        language="中文", itn=True,
    )
    time_nano = time.time() - start
    text_nano = res_nano[0]["text"]

    print(f"Fun-ASR-Nano:    {text_nano}")
    print(f"  耗时: {time_nano:.3f}s")

    print(f"\n--- 对比 ---")
    print(f"SenseVoiceSmall: {text_sv}  ({time_sv:.3f}s)")
    print(f"Fun-ASR-Nano:    {text_nano}  ({time_nano:.3f}s)")


def main():
    print("=" * 60)
    print("Fun-ASR-Nano-2512 能力测试")
    print("=" * 60)

    device = get_device()

    # 基础测试
    model = test_nano_basic(device)

    # 热词测试
    test_nano_hotword(model, device)

    # 自定义音频测试
    test_nano_custom_audio(model)

    # 与 SenseVoiceSmall 对比（可选，比较耗时）
    run_compare = input("\n是否运行 SenseVoiceSmall 对比测试？(y/N): ").strip().lower()
    if run_compare == "y":
        test_compare_sensevoice(device)

    print("\n" + "=" * 60)
    print("测试完成！")
    print("=" * 60)
    print("\n后续步骤:")
    print("1. 将包含专有名词的音频放入 test_fun_asr_nano/audio/ 目录")
    print("2. 修改脚本中的 hotwords 列表为你的专有名词")
    print("3. 重新运行脚本观察热词对识别效果的影响")


if __name__ == "__main__":
    main()
