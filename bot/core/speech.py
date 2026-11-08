import asyncio
import logging
import os
import time
from importlib.util import find_spec
from pathlib import Path

MAX_SECONDS = 300
SAMPLE_RATE = 16000
_log = logging.getLogger(__name__)
_lock = asyncio.Lock()
_model = None
_model_used_at = 0.0


def model_name() -> str:
    return os.getenv("WHISPER_MODEL") or "small"


def enabled() -> bool:
    return find_spec("faster_whisper") is not None and find_spec("av") is not None


def _decode(path: Path):
    import av
    import numpy as np

    formats = "ogg,matroska,webm,mov,mp4,m4a,wav,mp3,flac,aac"
    frames, samples = [], 0
    with av.open(str(path), options={"protocol_whitelist": "file", "format_whitelist": formats}) as container:
        if not container.streams.audio:
            raise ValueError("В записи нет звуковой дорожки")
        if container.duration and container.duration > MAX_SECONDS * av.time_base:
            raise ValueError("Запись длиннее пяти минут")
        resampler = av.AudioResampler(format="fltp", layout="mono", rate=SAMPLE_RATE)
        for frame in container.decode(audio=0):
            for audio in resampler.resample(frame):
                samples += audio.samples
                if samples > MAX_SECONDS * SAMPLE_RATE:
                    raise ValueError("Запись длиннее пяти минут")
                frames.append(audio.to_ndarray().reshape(-1))
    if frames:
        return np.concatenate(frames)
    return np.empty(0, dtype='float32')


def _whisper(audio) -> str:
    from faster_whisper import WhisperModel

    global _model, _model_used_at
    if _model is None:
        _model = WhisperModel(model_name(), device="cpu", compute_type="int8",
                              cpu_threads=min(os.cpu_count() or 1, 4), download_root=os.getenv("WHISPER_DIR"))
    try:
        segments, _ = _model.transcribe(audio, language="ru", vad_filter=True, beam_size=3,
                                        condition_on_previous_text=False)
        return " ".join(segment.text.strip() for segment in segments).strip()
    finally:
        _model_used_at = time.monotonic()


async def recognize(path: Path) -> str:
    async with _lock:
        audio = await asyncio.to_thread(_decode, path)
        if not len(audio):
            return ""
        return await asyncio.to_thread(_whisper, audio)


async def unload_idle():
    global _model
    if _model is not None and not _lock.locked() and time.monotonic() - _model_used_at > 15 * 60:
        _model = None
