"""Offline KWS smoke test and single-stream CPU/RSS benchmark (synthetic samples)."""
import json, time
from pathlib import Path
import numpy as np
import psutil
import sherpa_onnx
import soundfile as sf
from scipy.signal import resample_poly

root = Path(__file__).resolve().parents[1]
model = root / "apps-src/patient/public/wakeword/sherpa-onnx-kws-zipformer-wenetspeech-3.3M-2024-01-01"
process = psutil.Process()
baseline = process.memory_info().rss
start = time.perf_counter()
spotter = sherpa_onnx.KeywordSpotter(
    tokens=str(model / "tokens.txt"),
    encoder=str(model / "encoder-epoch-12-avg-2-chunk-16-left-64.onnx"),
    decoder=str(model / "decoder-epoch-12-avg-2-chunk-16-left-64.onnx"),
    joiner=str(model / "joiner-epoch-12-avg-2-chunk-16-left-64.onnx"),
    keywords_file=str(model / "keywords_anan.txt"),
    num_threads=2, sample_rate=16000, feature_dim=80,
    max_active_paths=4, keywords_score=1.0, keywords_threshold=0.5,
    num_trailing_blanks=1, provider="cpu",
)
report = {"load_seconds": round(time.perf_counter()-start,3), "model_rss_mib": round((process.memory_info().rss-baseline)/2**20,2), "tests": []}
def detect(audio):
    stream = spotter.create_stream()
    hits=[]
    for i in range(0,len(audio),4096):
        stream.accept_waveform(16000,audio[i:i+4096])
        while spotter.is_ready(stream): spotter.decode_stream(stream)
        result=spotter.get_result(stream)
        if result:
            hits.append(result)
            spotter.reset_stream(stream)
    return hits
rng=np.random.default_rng(42)
samples=[]
for name in ("anan","hello","negative"):
    audio,sr=sf.read(root / f"test/fixtures/wakeword/{name}.mp3",dtype="float32")
    if audio.ndim>1: audio=audio.mean(axis=1)
    audio=resample_poly(audio,16000,sr).astype(np.float32)
    samples.append(audio)
    for snr in (None,20,10,0):
        mixed=audio.copy()
        if snr is not None:
            mixed += rng.normal(0,np.sqrt(np.mean(audio**2))*10**(-snr/20),len(audio)).astype(np.float32)
        padded=np.concatenate([np.zeros(8000,dtype=np.float32),mixed,np.zeros(16000,dtype=np.float32)])
        report["tests"].append({"sample":name,"snr_db":snr,"hits":detect(padded)})
audio=np.tile(np.concatenate(samples),20)
seconds=len(audio)/16000
cpu0=sum(process.cpu_times()[:2]);wall=time.perf_counter()
detect(audio)
cpu=sum(process.cpu_times()[:2])-cpu0;elapsed=time.perf_counter()-wall
report.update(audio_seconds=round(seconds,2),decode_wall_seconds=round(elapsed,3),cpu_seconds=round(cpu,3),single_stream_one_core_percent=round(cpu/seconds*100,2),wall_realtime_factor=round(elapsed/seconds,4),rss_mib=round(process.memory_info().rss/2**20,2))
out=root / "test/fixtures/wakeword/benchmark.json"
out.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps(report,ensure_ascii=False,indent=2))
