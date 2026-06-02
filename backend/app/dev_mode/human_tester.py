"""human_tester — 人类测试员/检查官 (开发模式 verify 第三路, 区别于跑测试/Playwright).

像真人一样: bee-vision 截屏看界面 → 视觉模型(带严格 QA persona)决定下一步 →
OCR 锚定目标文字坐标 → bee-input 真点/真输入 → 再截屏校验 → 记 pass/fail。
全程 best-effort: 任何一步失败都记 fail 并继续/收尾, 不抛错阻断 PR。

前置: PC 上被测应用已启动且可见; PC 常驻 bee-vision(:8006)+bee-input(:8008)。
视觉模型走 litellm(需 vision-capable, env BEE_DEV_QA_MODEL; 空则用 hub 默认, 用户须配视觉模型)。
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

import yaml

from ..tools.seven_clients import bee_clients

_QA_MODEL = os.environ.get("BEE_DEV_QA_MODEL", "")  # 空=用 hub 默认(须 vision-capable)
_MAX_STEPS = int(os.environ.get("BEE_DEV_QA_MAX_STEPS", "20"))


def _persona() -> tuple[str, str]:
    """返回 (role 系统提示, output_contract)."""
    try:
        p = Path(__file__).resolve().parent.parent / "prompts" / "human_qa_persona.yaml"
        d = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        return str(d.get("role", "")), str(d.get("output_contract", ""))
    except Exception:
        return ("你是严格的人工 QA, 像真人一样用界面并挑剔地检查。", "只输出一个 JSON 动作对象。")


def _box_center(box: Any) -> tuple[int, int] | None:
    """OCR box 是 4 点四边形 [[x,y]*4]; 取中心。"""
    try:
        xs = [float(pt[0]) for pt in box]
        ys = [float(pt[1]) for pt in box]
        return int(sum(xs) / len(xs)), int(sum(ys) / len(ys))
    except Exception:
        return None


def _find_target(boxes: list[dict[str, Any]], target_text: str) -> tuple[int, int] | None:
    """在 OCR 框里找包含 target_text 的(双向包含), 取分最高的中心坐标。"""
    t = (target_text or "").strip().lower()
    if not t:
        return None
    best, best_score = None, -1.0
    for b in boxes:
        bt = str(b.get("text", "")).strip().lower()
        if not bt:
            continue
        if t in bt or bt in t:
            sc = float(b.get("score", 0) or 0)
            if sc > best_score:
                best_score, best = sc, b.get("box")
    return _box_center(best) if best is not None else None


def _parse_action(text: str) -> dict[str, Any]:
    s = (text or "").strip()
    a, b = s.find("{"), s.rfind("}")
    if a == -1 or b == -1 or b < a:
        return {}
    try:
        d = json.loads(s[a:b + 1])
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


async def _screenshot() -> dict[str, Any]:
    return await asyncio.to_thread(bee_clients.screenshot, 1, None)


async def run_human_test(*, test_points: list[str], dev_id: str = "",
                         max_steps: int = 0) -> dict[str, Any]:
    """对当前 PC 屏幕上的被测应用做人工走查。返回 HumanTestReport {points,passed,failed}。"""
    role, contract = _persona()
    steps_cap = max_steps or _MAX_STEPS
    points: list[dict[str, Any]] = []
    history: list[str] = []
    plan_txt = "\n".join(f"- {p}" for p in (test_points or [])) or "(自由探索: 像真人一样把主要功能走一遍)"

    try:
        from ..llm.litellm_client import litellm_client
    except Exception:
        return {"points": [], "passed": 0, "failed": 0, "note": "litellm 不可用, 人工走查跳过"}

    for step in range(steps_cap):
        shot = await _screenshot()
        b64 = shot.get("image_b64")
        if not b64:
            points.append({"step": f"step{step}", "result": "fail", "note": f"截屏失败: {str(shot)[:160]}"})
            break
        data_url = f"data:{shot.get('mime', 'image/png')};base64,{b64}"
        sys = f"{role}\n\n{contract}"
        prompt = (f"[本次要走查的测试点]\n{plan_txt}\n\n"
                  f"[已做过的动作]\n{chr(10).join(history[-8:]) or '(无)'}\n\n"
                  "看当前截图, 决定下一个动作(JSON)。全部测试点走完就用 action=done。")
        try:
            resp = await litellm_client.complete(model=_QA_MODEL, fallbacks=[], prompt=prompt,
                                                 system=sys, images=[data_url])
            act = _parse_action(resp.text)
        except Exception as e:
            points.append({"step": f"step{step}", "result": "fail", "note": f"视觉模型调用失败: {str(e)[:160]}"})
            break
        if not act:
            history.append(f"step{step}: 模型未给出有效动作")
            continue

        action = str(act.get("action", "")).lower()
        note = str(act.get("point_note", "")).strip()
        if note:
            res = "pass" if "pass" in note.lower() else ("fail" if "fail" in note.lower() else "info")
            points.append({"step": str(act.get("expected", ""))[:120] or f"step{step}",
                           "action": action, "target": act.get("target_text", ""),
                           "result": res, "note": note[:300]})
        if action == "done":
            break

        if action in ("click", "type"):
            ocr = await asyncio.to_thread(bee_clients.ocr, b64, "rapidocr")
            center = _find_target(ocr.get("boxes", []), str(act.get("target_text", "")))
            if not center:
                history.append(f"step{step}: 找不到 '{act.get('target_text','')}'(OCR 未锚定), 跳过")
                points.append({"step": str(act.get("target_text", "")), "action": action,
                               "result": "fail", "note": "OCR 未在界面找到该目标(可能未渲染/被遮挡)"})
                continue
            x, y = center
            try:
                await asyncio.to_thread(bee_clients.input_move, x, y)
                await asyncio.to_thread(bee_clients.input_click, x, y)
                if action == "type" and act.get("input_text"):
                    await asyncio.to_thread(bee_clients.input_type, str(act.get("input_text")))
                history.append(f"step{step}: {action} '{act.get('target_text','')}' @({x},{y})")
            except Exception as e:
                history.append(f"step{step}: 点击/输入失败 {str(e)[:120]}")
                points.append({"step": str(act.get("target_text", "")), "action": action,
                               "result": "fail", "note": f"bee-input 失败: {str(e)[:160]}"})
            await asyncio.sleep(0.8)  # 等界面响应再截下一帧
        elif action == "scroll":
            history.append(f"step{step}: scroll (略)")
            await asyncio.sleep(0.3)

    passed = sum(1 for p in points if p.get("result") == "pass")
    failed = sum(1 for p in points if p.get("result") == "fail")
    report = {"points": points, "passed": passed, "failed": failed, "steps_used": min(steps_cap, len(history) + 1)}
    if dev_id:
        try:
            from ..stream_bus import bus
            from ..models import StreamEvent
            bus.publish(StreamEvent(type="dev_human_qa", decision_id=dev_id,
                                    payload={"passed": passed, "failed": failed, "points": len(points)}))
        except Exception:
            pass
    return report
