"""v1.6 多模态 - 语音输出 (edge-tts 免费). Scaffold."""
from __future__ import annotations


def synthesize(text: str, voice: str = "zh-CN-XiaoxiaoNeural") -> dict:
    return {"audio_path": "", "scaffold": True, "voice": voice}