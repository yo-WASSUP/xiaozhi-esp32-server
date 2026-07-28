from __future__ import annotations

import asyncio
import queue
import threading
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


PCM_WIDTH_BYTES = 2


def load_script_env(script_file: str) -> None:
    load_dotenv(Path(script_file).resolve().with_name(".env"))


def require_env(name: str) -> str:
    import os

    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"缺少环境变量 {name}，请先填写当前目录的 .env")
    return value


def _load_pyaudio() -> Any:
    try:
        import pyaudio
    except ImportError as exc:
        raise RuntimeError(
            "缺少 PyAudio，请在 realtime-voice-api-tests 目录执行 "
            "python -m pip install -r requirements.txt"
        ) from exc
    return pyaudio


class PcmMicrophone:
    """20 ms PCM16 mono microphone source backed by a PyAudio callback."""

    def __init__(self, sample_rate: int, chunk_ms: int = 20) -> None:
        self.sample_rate = sample_rate
        self.chunk_ms = chunk_ms
        self.frames_per_buffer = sample_rate * chunk_ms // 1000
        self._chunks: queue.Queue[bytes | None] = queue.Queue(maxsize=100)
        self._pyaudio = _load_pyaudio()
        self._audio = self._pyaudio.PyAudio()
        self._closed = False
        self._stream = self._audio.open(
            format=self._pyaudio.paInt16,
            channels=1,
            rate=sample_rate,
            input=True,
            frames_per_buffer=self.frames_per_buffer,
            stream_callback=self._callback,
            start=True,
        )

    def _callback(
        self,
        in_data: bytes,
        frame_count: int,
        time_info: dict[str, float],
        status_flags: int,
    ) -> tuple[None, int]:
        del frame_count, time_info, status_flags
        if self._closed:
            return None, self._pyaudio.paComplete
        try:
            self._chunks.put_nowait(in_data)
        except queue.Full:
            try:
                self._chunks.get_nowait()
            except queue.Empty:
                pass
            try:
                self._chunks.put_nowait(in_data)
            except queue.Full:
                pass
        return None, self._pyaudio.paContinue

    async def read(self) -> bytes:
        while not self._closed:
            try:
                chunk = await asyncio.to_thread(self._chunks.get, True, 0.2)
            except queue.Empty:
                continue
            if chunk is None:
                break
            return chunk
        raise EOFError("麦克风已关闭")

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self._chunks.put_nowait(None)
        except queue.Full:
            pass
        if self._stream.is_active():
            self._stream.stop_stream()
        self._stream.close()
        self._audio.terminate()

    def __enter__(self) -> "PcmMicrophone":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()


class PcmPlayer:
    """Non-blocking PCM16 mono output with an instantly clearable buffer."""

    def __init__(self, sample_rate: int, frames_per_buffer: int = 960) -> None:
        self.sample_rate = sample_rate
        self._buffer = bytearray()
        self._lock = threading.Lock()
        self._pyaudio = _load_pyaudio()
        self._audio = self._pyaudio.PyAudio()
        self._closed = False
        self._stream = self._audio.open(
            format=self._pyaudio.paInt16,
            channels=1,
            rate=sample_rate,
            output=True,
            frames_per_buffer=frames_per_buffer,
            stream_callback=self._callback,
            start=True,
        )

    def _callback(
        self,
        in_data: bytes | None,
        frame_count: int,
        time_info: dict[str, float],
        status_flags: int,
    ) -> tuple[bytes, int]:
        del in_data, time_info, status_flags
        wanted = frame_count * PCM_WIDTH_BYTES
        with self._lock:
            take = min(wanted, len(self._buffer))
            output = bytes(self._buffer[:take])
            del self._buffer[:take]
        if take < wanted:
            output += bytes(wanted - take)
        flag = self._pyaudio.paComplete if self._closed else self._pyaudio.paContinue
        return output, flag

    def enqueue(self, audio: bytes) -> None:
        if not audio or self._closed:
            return
        with self._lock:
            self._buffer.extend(audio)

    def clear(self) -> int:
        with self._lock:
            dropped_bytes = len(self._buffer)
            self._buffer.clear()
        return int(dropped_bytes * 1000 / (self.sample_rate * PCM_WIDTH_BYTES))

    @property
    def queued_ms(self) -> int:
        with self._lock:
            size = len(self._buffer)
        return int(size * 1000 / (self.sample_rate * PCM_WIDTH_BYTES))

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.clear()
        if self._stream.is_active():
            self._stream.stop_stream()
        self._stream.close()
        self._audio.terminate()

    def __enter__(self) -> "PcmPlayer":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()


async def run_until_one_stops(*coroutines: Any) -> None:
    tasks = [asyncio.create_task(coro) for coro in coroutines]
    try:
        done, _ = await asyncio.wait(
            tasks,
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in done:
            task.result()
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
