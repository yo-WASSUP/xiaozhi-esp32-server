"""Run once before starting hospice: python scripts/setup_symptom_model.py."""
from pathlib import Path
import requests

DESTINATION = Path(__file__).resolve().parents[1] / "models" / "bge-small-zh-v1.5"
BASE = "https://huggingface.co/Xenova/bge-small-zh-v1.5/resolve/main/"


def main():
    DESTINATION.mkdir(parents=True, exist_ok=True)
    for name in ("tokenizer.json", "onnx/model_quantized.onnx"):
        destination = DESTINATION / name.split("/")[-1]
        temporary = destination.with_suffix(destination.suffix + ".download")
        with requests.get(BASE + name, timeout=(15, 120), stream=True) as response:
            response.raise_for_status()
            with temporary.open("wb") as output:
                for chunk in response.iter_content(1024 * 1024):
                    output.write(chunk)
        temporary.replace(destination)
        print(destination)


if __name__ == "__main__":
    main()
