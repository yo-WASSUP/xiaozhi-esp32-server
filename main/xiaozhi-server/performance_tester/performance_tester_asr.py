import asyncio
import logging
import os
import time
from typing import Dict

import aiohttp
from tabulate import tabulate
from core.utils.asr import create_instance as create_stt_instance
from config.settings import load_config

# 设置全局日志级别为WARNING，抑制INFO级别日志
logging.basicConfig(level=logging.WARNING)

description = "语音识别模型性能测试"


class ASRPerformanceTester:
    def __init__(self):
        self.config = load_config()
        self.test_wav_list = self._load_test_wav_files()
        self.results = {"stt": {}}

        # 调试日志
        print(f"[DEBUG] 加载的ASR配置: {self.config.get('ASR', {})}")
        print(f"[DEBUG] 音频文件数量: {len(self.test_wav_list)}")

    def _load_test_wav_files(self) -> list:
        """加载测试用的音频文件（添加路径调试）"""
        wav_root = os.path.join(os.getcwd(), "config", "assets")
        print(f"[DEBUG] 音频文件目录: {wav_root}")
        test_wav_list = []

        if os.path.exists(wav_root):
            file_list = os.listdir(wav_root)
            print(f"[DEBUG] 找到音频文件: {file_list}")
            for file_name in file_list:
                file_path = os.path.join(wav_root, file_name)
                if os.path.getsize(file_path) > 300 * 1024:  # 300KB
                    with open(file_path, "rb") as f:
                        test_wav_list.append(f.read())
        else:
            print(f" 目录不存在: {wav_root}")
        return test_wav_list

    async def _test_stt(self, stt_name: str, config: Dict) -> Dict:
        """异步测试单个STT性能（跳过无效配置）"""
        try:
            token_fields = ["access_token", "api_key", "token"]
            # 忽略值为 "none" 的情况（需根据实际需求调整）
            if any(
                field in config
                and str(config[field]).lower() in ["你的", "placeholder"]
                for field in token_fields
            ):
                print(f"  STT {stt_name} 未配置access_token/api_key，已跳过")
                return {"name": stt_name, "type": "stt", "errors": 1}

            module_type = config.get("type", stt_name)
            stt = create_stt_instance(module_type, config, delete_audio_file=True)
            stt.audio_format = "pcm"

            print(f" 测试 STT: {stt_name}")

            # 测试第一个音频文件
            text, _ = await stt.speech_to_text(
                [self.test_wav_list[0]], "1", stt.audio_format
            )
            if text is None:
                print(f" {stt_name} 连接失败")
                return {"name": stt_name, "type": "stt", "errors": 1}

            # 全量测试
            total_time = 0
            test_count = len(self.test_wav_list)
            for i, sentence in enumerate(self.test_wav_list, 1):
                start = time.time()
                text, _ = await stt.speech_to_text([sentence], "1", stt.audio_format)
                duration = time.time() - start
                total_time += duration
                print(f" {stt_name} [{i}/{test_count}] 耗时: {duration:.2f}s")

            return {
                "name": stt_name,
                "type": "stt",
                "avg_time": total_time / test_count,
                "errors": 0,
            }
        except Exception as e:
            print(f"⚠️ {stt_name} 测试失败: {str(e)}")
            return {"name": stt_name, "type": "stt", "errors": 1}

    def _print_results(self):
        """打印测试结果"""
        stt_table = []
        for name, data in self.results["stt"].items():
            if data["errors"] == 0:
                stt_table.append([name, f"{data['avg_time']:.3f}秒"])

        if stt_table:
            print("\nASR 性能排行:\n")
            print(
                tabulate(
                    stt_table,
                    headers=["模型名称", "平均耗时"],
                    tablefmt="github",
                    colalign=("left", "right"),
                )
            )
        else:
            print("\n 没有可用的ASR模块进行测试。")

    async def run(self):
        """执行全量异步测试"""
        print("开始筛选可用ASR模块...")
        if not self.config.get("ASR"):
            print("配置中未找到 ASR 模块")
            return

        all_tasks = []
        for stt_name, config in self.config["ASR"].items():
            print(f"[DEBUG] 检查 ASR 模块: {stt_name}, 配置: {config}")
            all_tasks.append(self._test_stt(stt_name, config))

        if not all_tasks:
            print("没有可用的ASR模块进行测试。")
            return

        print("\n开始并发测试所有ASR模块...")
        all_results = await asyncio.gather(*all_tasks, return_exceptions=True)

        # 处理结果
        for result in all_results:
            if isinstance(result, dict) and result.get("type") == "stt":
                if result["errors"] == 0:
                    self.results["stt"][result["name"]] = result

        # 打印结果
        print("\n测试完成")
        self._print_results()


async def main():
    tester = ASRPerformanceTester()
    await tester.run()


if __name__ == "__main__":
    asyncio.run(main())
