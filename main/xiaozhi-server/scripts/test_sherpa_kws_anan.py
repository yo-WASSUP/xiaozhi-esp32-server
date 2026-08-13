"""Quick local test for the sherpa-onnx "安安" wake word model.

Usage:
  python scripts/test_sherpa_kws_anan.py --mic
  python scripts/test_sherpa_kws_anan.py --wav path/to/test.wav
  python scripts/test_sherpa_kws_anan.py --list-devices
"""

from __future__ import annotations

import argparse
import queue
import sys
import time
import wave
from pathlib import Path

import numpy as np
import sherpa_onnx


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL_DIR = (
    ROOT
    / "apps-src"
    / "patient"
    / "public"
    / "wakeword"
    / "sherpa-onnx-kws-zipformer-wenetspeech-3.3M-2024-01-01"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Test sherpa-onnx KWS for 安安.")
    parser.add_argument("--model-dir", type=Path, default=DEFAULT_MODEL_DIR)
    parser.add_argument("--keywords", default="keywords_anan.txt")
    parser.add_argument("--threshold", type=float, default=0.50)
    parser.add_argument("--sample-rate", type=int, default=16000)
    parser.add_argument("--chunk-ms", type=int, default=100)
    parser.add_argument("--device", default=None, help="sounddevice input device id/name")
    parser.add_argument("--duration", type=float, default=0.0, help="mic test seconds; 0 means run until Ctrl+C")
    parser.add_argument("--cooldown", type=float, default=1.5, help="seconds to suppress repeated wake logs")
    parser.add_argument("--mic", action="store_true", help="listen from microphone")
    parser.add_argument("--wav", type=Path, help="detect from a wav file")
    parser.add_argument("--list-devices", action="store_true")
    parser.add_argument("--int8", action="store_true", help="use int8 onnx files")
    return parser.parse_args()


def model_file(model_dir: Path, stem: str, int8: bool) -> str:
    suffix = ".int8.onnx" if int8 else ".onnx"
    return str(model_dir / f"{stem}{suffix}")


def create_spotter(args: argparse.Namespace) -> sherpa_onnx.KeywordSpotter:
    model_dir = args.model_dir.resolve()
    if not model_dir.exists():
        raise FileNotFoundError(f"Model dir not found: {model_dir}")

    keywords_file = model_dir / args.keywords
    if not keywords_file.exists():
        raise FileNotFoundError(f"Keywords file not found: {keywords_file}")

    return sherpa_onnx.KeywordSpotter(
        tokens=str(model_dir / "tokens.txt"),
        encoder=model_file(
            model_dir, "encoder-epoch-12-avg-2-chunk-16-left-64", args.int8
        ),
        decoder=model_file(
            model_dir, "decoder-epoch-12-avg-2-chunk-16-left-64", args.int8
        ),
        joiner=model_file(
            model_dir, "joiner-epoch-12-avg-2-chunk-16-left-64", args.int8
        ),
        keywords_file=str(keywords_file),
        num_threads=2,
        sample_rate=args.sample_rate,
        feature_dim=80,
        max_active_paths=4,
        keywords_score=1.0,
        keywords_threshold=args.threshold,
        num_trailing_blanks=1,
        provider="cpu",
    )


def read_wav(path: Path, target_sample_rate: int) -> tuple[int, np.ndarray]:
    with wave.open(str(path), "rb") as f:
        sample_rate = f.getframerate()
        channels = f.getnchannels()
        sample_width = f.getsampwidth()
        frames = f.readframes(f.getnframes())

    if sample_width != 2:
        raise ValueError(f"Only 16-bit PCM wav is supported, got {sample_width * 8}-bit")

    samples = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1)

    if sample_rate != target_sample_rate:
        old_x = np.arange(len(samples), dtype=np.float32)
        new_len = int(len(samples) * target_sample_rate / sample_rate)
        new_x = np.linspace(0, len(samples) - 1, num=new_len, dtype=np.float32)
        samples = np.interp(new_x, old_x, samples).astype(np.float32)
        sample_rate = target_sample_rate

    return sample_rate, samples


def decode_samples(
    spotter: sherpa_onnx.KeywordSpotter,
    sample_rate: int,
    samples: np.ndarray,
    chunk_size: int,
) -> list[str]:
    stream = spotter.create_stream()
    results: list[str] = []

    for start in range(0, len(samples), chunk_size):
        chunk = samples[start : start + chunk_size]
        stream.accept_waveform(sample_rate, chunk)
        while spotter.is_ready(stream):
            spotter.decode_stream(stream)
        result = spotter.get_result(stream)
        if result:
            results.append(result)
            spotter.reset_stream(stream)

    stream.accept_waveform(sample_rate, np.zeros(int(0.5 * sample_rate), dtype=np.float32))
    stream.input_finished()
    while spotter.is_ready(stream):
        spotter.decode_stream(stream)

    result = spotter.get_result(stream)
    if result:
        results.append(result)

    return results


def run_wav(args: argparse.Namespace) -> int:
    spotter = create_spotter(args)
    sample_rate, samples = read_wav(args.wav, args.sample_rate)
    chunk_size = max(1, int(sample_rate * args.chunk_ms / 1000))
    results = decode_samples(spotter, sample_rate, samples, chunk_size)

    print(f"wav: {args.wav}")
    print(f"duration: {len(samples) / sample_rate:.2f}s")
    if results:
        for item in results:
            print(f"WAKE: {item}")
        return 0

    print("NO_WAKE")
    return 1


def run_mic(args: argparse.Namespace) -> int:
    import sounddevice as sd

    spotter = create_spotter(args)
    sample_rate = args.sample_rate
    chunk_size = max(1, int(sample_rate * args.chunk_ms / 1000))
    audio_queue: queue.Queue[np.ndarray] = queue.Queue()
    device = int(args.device) if isinstance(args.device, str) and args.device.isdigit() else args.device

    def callback(indata, frames, callback_time, status):
        if status:
            print(status, file=sys.stderr)
        audio_queue.put(indata[:, 0].copy())

    stream = spotter.create_stream()
    print("Listening for 安安 / 你好安安. Press Ctrl+C to stop.")
    print(f"sample_rate={sample_rate}, chunk_size={chunk_size}, threshold={args.threshold}")

    try:
        with sd.InputStream(
            samplerate=sample_rate,
            blocksize=chunk_size,
            channels=1,
            dtype="float32",
            device=device,
            callback=callback,
        ):
            last_heartbeat = 0.0
            last_wake = 0.0
            started_at = time.time()
            while True:
                if args.duration > 0 and time.time() - started_at >= args.duration:
                    print("Time is up.")
                    return 0

                chunk = audio_queue.get()
                stream.accept_waveform(sample_rate, chunk)
                while spotter.is_ready(stream):
                    spotter.decode_stream(stream)

                result = spotter.get_result(stream)
                if result:
                    now = time.time()
                    if now - last_wake >= args.cooldown:
                        print(f"[{time.strftime('%H:%M:%S')}] WAKE: {result}")
                        last_wake = now
                    spotter.reset_stream(stream)

                now = time.time()
                if now - last_heartbeat > 5:
                    print(f"[{time.strftime('%H:%M:%S')}] listening...")
                    last_heartbeat = now
    except KeyboardInterrupt:
        print("\nStopped.")
        return 0


def list_devices() -> int:
    import sounddevice as sd

    print(sd.query_devices())
    return 0


def main() -> int:
    args = parse_args()
    if args.list_devices:
        return list_devices()
    if args.wav:
        return run_wav(args)
    if args.mic:
        return run_mic(args)

    print("Please pass --mic, --wav, or --list-devices.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
