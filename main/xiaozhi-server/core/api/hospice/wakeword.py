"""Wake-word websocket endpoint for the patient app."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from aiohttp import WSMsgType, web

from config.logger import setup_logging

TAG = __name__
logger = setup_logging()


class HospiceWakeWordMixin:
    def _wakeword_config(self) -> dict:
        hospice = self.config.get("hospice", {}) or {}
        return {
            "enabled": hospice.get("enable_patient_wakeup", True),
            "threshold": float(hospice.get("patient_wakeup_threshold", 0.50)),
            "sherpa_onnx": hospice.get("patient_wakeup_sherpa_onnx", {}) or {},
        }

    def _resolve_wakeword_asset(self, value: str) -> Path:
        path = str(value or "").strip()
        server_root = Path(__file__).resolve().parents[3]
        if path.startswith("/wakeword/"):
            return server_root / "apps-src" / "patient" / "public" / path.lstrip("/")
        p = Path(path)
        if p.is_absolute():
            return p
        return server_root / p

    def _get_wakeword_spotter(self):
        spotter = getattr(self, "_wakeword_spotter", None)
        if spotter is not None:
            return spotter

        import sherpa_onnx

        cfg = self._wakeword_config()
        sherpa_cfg = cfg["sherpa_onnx"]
        model_dir = self._resolve_wakeword_asset(
            sherpa_cfg.get("model_dir")
            or "/wakeword/sherpa-onnx-kws-zipformer-wenetspeech-3.3M-2024-01-01"
        )
        keywords = sherpa_cfg.get("keywords") or "keywords_xiaonuan.txt"

        def pick(name: str, default: str) -> str:
            return str(model_dir / (sherpa_cfg.get(name) or default))

        spotter = sherpa_onnx.KeywordSpotter(
            tokens=str(model_dir / (sherpa_cfg.get("tokens") or "tokens.txt")),
            encoder=pick("encoder", "encoder-epoch-12-avg-2-chunk-16-left-64.onnx"),
            decoder=pick("decoder", "decoder-epoch-12-avg-2-chunk-16-left-64.onnx"),
            joiner=pick("joiner", "joiner-epoch-12-avg-2-chunk-16-left-64.onnx"),
            keywords_file=str(model_dir / keywords),
            num_threads=int(sherpa_cfg.get("num_threads") or 2),
            sample_rate=int(sherpa_cfg.get("sample_rate") or 16000),
            feature_dim=int(sherpa_cfg.get("feature_dim") or 80),
            max_active_paths=int(sherpa_cfg.get("max_active_paths") or 4),
            keywords_score=1.0,
            keywords_threshold=cfg["threshold"],
            num_trailing_blanks=1,
            provider=sherpa_cfg.get("provider") or "cpu",
        )
        self._wakeword_spotter = spotter
        logger.bind(tag=TAG).info(f"患者端唤醒词模型已加载: {model_dir}")
        return spotter

    async def handle_wakeword_ws(self, request):
        """GET /api/hospice/wakeword/ws

        Binary frames are signed 16-bit little-endian PCM. The first optional
        JSON message may set {"type":"start","sample_rate":48000}.
        """

        ws = web.WebSocketResponse(heartbeat=20)
        await ws.prepare(request)

        cfg = self._wakeword_config()
        if not cfg["enabled"]:
            await ws.send_json({"type": "error", "message": "wake word disabled"})
            await ws.close()
            return ws

        try:
            spotter = self._get_wakeword_spotter()
            stream = spotter.create_stream()
        except Exception as exc:
            logger.bind(tag=TAG).error(f"唤醒词模型初始化失败: {exc}")
            await ws.send_json({"type": "error", "message": str(exc)})
            await ws.close()
            return ws

        sample_rate = int((cfg["sherpa_onnx"] or {}).get("sample_rate") or 16000)
        await ws.send_json({"type": "ready", "sample_rate": sample_rate})

        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                try:
                    payload = json.loads(msg.data)
                except Exception:
                    continue
                if payload.get("type") == "start":
                    sample_rate = int(payload.get("sample_rate") or sample_rate)
                    await ws.send_json({"type": "started", "sample_rate": sample_rate})
                elif payload.get("type") == "reset":
                    spotter.reset_stream(stream)
                continue

            if msg.type != WSMsgType.BINARY:
                continue

            samples = np.frombuffer(msg.data, dtype="<i2").astype(np.float32) / 32768.0
            if samples.size == 0:
                continue

            stream.accept_waveform(sample_rate, samples)
            while spotter.is_ready(stream):
                spotter.decode_stream(stream)

            result = spotter.get_result(stream)
            if result:
                await ws.send_json({"type": "wake", "keyword": result})
                spotter.reset_stream(stream)

        return ws
