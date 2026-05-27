"""v1.6 多模态 - 本地 Whisper (faster-whisper, large-v3). Scaffold."""
from __future__ import annotations


def transcribe(audio_path: str) -> dict:
    return {"text": "", "scaffold": True, "model": "faster-whisper:large-v3"}