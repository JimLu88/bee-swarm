"""v1.6 多模态 - Claude Vision via LiteLLM. Scaffold.
完整实现:调 D:\\AI\\AI 视觉中心 的 /vision/describe.
"""
from __future__ import annotations


def describe_image(image_path: str, question: str = "描述图片") -> dict:
    return {"description": "", "scaffold": True}