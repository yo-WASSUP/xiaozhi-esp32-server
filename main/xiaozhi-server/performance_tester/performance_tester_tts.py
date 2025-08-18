import asyncio
import logging
import os
import time
from typing import Dict
import yaml
from tabulate import tabulate

# 确保从 core.utils.tts 导入 create_tts_instance
from core.utils.tts import create_instance as create_tts_instance
from config.settings import load_config

# 设置全局日志级别为 WARNING
logging.basicConfig(level=logging.WARNING)

description = "非流式语音合成性能测试"


class TTSPerformanceTester:
    def __init__(self):
        self.config = load_config()
        self.test_sentences = self.config.get("module_test", {}).get(
            "test_sentences",
            [
                "永和九年，岁在癸丑，暮春之初；",
                "夫人之相与，俯仰一世，或取诸怀抱，悟言一室之内；或因寄所托，放浪形骸之外。虽趣舍万殊，静躁不同，",
                "每览昔人兴感之由，若合一契，未尝不临文嗟悼，不能喻之于怀。固知一死生为虚诞，齐彭殇为妄作。",
            ],
        )
        self.results = {}

    async def _test_tts(self, tts_name: str, config: Dict) -> Dict:
        """测试单个TTS模块的性能"""
        try:
            token_fields = ["access_token", "api_key", "token"]
            if any(
                field in config
                and any(x in config[field] for x in ["你的", "placeholder"])
                for field in token_fields
            ):
                print(f"TTS {tts_name} 未配置access_token/api_key，已跳过")
                return {"name": tts_name, "errors": 1}

            module_type = config.get("type", tts_name)
            tts = create_tts_instance(module_type, config, delete_audio_file=True)

            print(f"测试 TTS: {tts_name}")

            # 连接测试
            tmp_file = tts.generate_filename()
            await tts.text_to_speak("连接测试", tmp_file)

            if not tmp_file or not os.path.exists(tmp_file):
                print(f"{tts_name} 连接失败")
                return {"name": tts_name, "errors": 1}

            total_time = 0
            test_count = len(self.test_sentences[:3])

            for i, sentence in enumerate(self.test_sentences[:2], 1):
                start = time.time()
                tmp_file = tts.generate_filename()
                await tts.text_to_speak(sentence, tmp_file)
                duration = time.time() - start
                total_time += duration

                if tmp_file and os.path.exists(tmp_file):
                    print(f"{tts_name} [{i}/{test_count}] 测试成功")
                else:
                    print(f"{tts_name} [{i}/{test_count}] 测试失败")
                    return {"name": tts_name, "errors": 1}

            return {
                "name": tts_name,
                "avg_time": total_time / test_count,
                "errors": 0,
            }

        except Exception as e:
            print(f"{tts_name} 测试失败: {str(e)}")
            return {"name": tts_name, "errors": 1}

    def _print_results(self):
        """打印测试结果"""
        if not self.results:
            print("没有有效的TTS测试结果")
            return

        table = []
        for name, data in self.results.items():
            if data["errors"] == 0:
                table.append(
                    [name, f"{data['avg_time']:.3f}秒/句", len(self.test_sentences[:3])]
                )

        print("\nTTS性能测试结果:")
        print(
            tabulate(
                table,
                headers=["TTS模块", "平均耗时", "测试句子数"],
                tablefmt="github",
                colalign=("left", "right", "right"),
            )
        )

    async def run(self):
        """执行测试"""
        print("开始TTS性能测试...")

        if not self.config.get("TTS"):
            print("配置文件中未找到TTS配置")
            return

        # 遍历所有TTS配置
        tasks = []
        for tts_name, config in self.config.get("TTS", {}).items():
            tasks.append(self._test_tts(tts_name, config))

        # 并发执行测试
        results = await asyncio.gather(*tasks)

        # 保存有效结果
        for result in results:
            if result["errors"] == 0:
                self.results[result["name"]] = result

        # 打印结果
        self._print_results()


# 为了performance_tester.py的调用需求
async def main():
    tester = TTSPerformanceTester()
    await tester.run()


if __name__ == "__main__":
    tester = TTSPerformanceTester()
    asyncio.run(tester.run())
