from __future__ import annotations

import asyncio
import hashlib
import json
import random
import time
import uuid
from typing import Any

from .gene_scoring import gene_score
from .models import DeptLeadReport, DecisionSummary, HeatmapCell, StreamEvent
from .modes import get_mode
from .decision_memory import DecisionMemory
from .config_store import ConfigStore
from .gene_defaults import build_initial_gene_prompt
from .gene_store import GeneStore
from .shadow_testing import ShadowTester
from .llm.litellm_client import litellm_client
from .llm.parsing import parse_dept_output
from .llm.router import router as llm_router
from .rag.retriever import retriever as rag_retriever
from .rag.summary_hints import compact_rag_hint_from_dept_rows
from .rag.trusted_weights import sort_rag_chunks_by_trusted
from .rag.types import RagChunk
from .search.benchmark_web import fetch_benchmark_web_chunks
from .settings_llm_rag import llm_rag_settings
from .execution import build_execution_bundle
from .stream_bus import bus
from .vision_scope import is_vision_dept
from .runtime_paths import backend_data_dir


_DATA = backend_data_dir()
_memory = DecisionMemory(_DATA)
_cfg = ConfigStore(_DATA)
_genes = GeneStore(_DATA)
_shadow = ShadowTester(_DATA)


def _stable_float(seed: str, lo: float = 0.0, hi: float = 1.0) -> float:
    h = hashlib.sha256(seed.encode("utf-8")).digest()
    n = int.from_bytes(h[:8], "big")
    r = (n % 10_000) / 10_000
    return lo + (hi - lo) * r


def _mk_debate_log_id(dept: str) -> str:
    return f"{dept}-{time.strftime('%Y%m%d')}-{uuid.uuid4().hex[:8]}"


def _rag_retrieval_meta(combined: list[RagChunk], web_chunks: list[RagChunk]) -> dict[str, Any]:
    """Operator-facing summary; chunk bodies stay in ``rag_context``."""
    hybrid_hits = sum(1 for c in combined if (c.meta or {}).get("hybrid") is True)
    lane_counts: dict[str, int] = {}
    for c in combined:
        lane = str((c.meta or {}).get("rag_lane") or "unknown")
        lane_counts[lane] = lane_counts.get(lane, 0) + 1
    return {
        "rag_backend": llm_rag_settings.rag_backend,
        "total_chunks": len(combined),
        "web_chunks": len(web_chunks),
        "hybrid_overlap_hits": hybrid_hits,
        "rag_lane_counts": lane_counts,
        "hybrid_local_fts_configured": llm_rag_settings.rag_hybrid_local_fts,
        "hybrid_merge_effective": llm_rag_settings.rag_backend == "qdrant" and llm_rag_settings.rag_hybrid_local_fts,
    }


async def _run_dept(
    decision_id: str,
    mode_id: str,
    dept: str,
    task: str,
    *,
    dispatcher_context: str = "",
    dispatcher_notes: str = "",
    task_level: str = "",
    task_urgency: str = "",
) -> DeptLeadReport:
    # MVP: simulated department run with deterministic scores.
    await asyncio.sleep(0.3 + _stable_float(f"{dept}:{task}", 0, 0.7))

    gene = _genes.get_active(mode_id=mode_id, dept=dept)
    if gene is None:
        gene = _genes.set_active(
            mode_id=mode_id,
            dept=dept,
            prompt=build_initial_gene_prompt(mode_id, dept),
        )
    from .gene_team import merged_gene_prompt

    gene_prompt = merged_gene_prompt(gene, mode_id, dept, f"你是 {dept} 部门的 Lead。")
    llm_choice = llm_router.pick_for_dept(dept)

    # Shadow gene (if any): run "in background" and score vs active.
    shadows = _genes.list_shadows(mode_id=mode_id, dept=dept, limit=1)
    shadow_rec = shadows[0] if shadows else None
    shadow_prompt = str(shadow_rec.get("prompt")) if shadow_rec else ""

    confidence = _stable_float(f"conf:{dept}:{task}", 0.15, 0.92)
    dissent = _stable_float(f"dis:{dept}:{task}", 0.05, 0.95)
    debate_log_id = _mk_debate_log_id(dept)

    rag_query = f"{task}\n{dispatcher_context}" if dispatcher_context else task

    web_chunks: list[RagChunk] = []
    web_meta: dict = {}
    web_limit = 3 if dept == "benchmark" else 2
    if is_vision_dept(dept) and llm_rag_settings.benchmark_web_search:
        web_chunks, web_meta = await fetch_benchmark_web_chunks(rag_query[:1200], limit=web_limit)

    rag_chunks = rag_retriever.retrieve(mode_id=mode_id, dept=dept, task=rag_query, k=5)

    if is_vision_dept(dept):
        trusted = (_cfg.get_config(mode_id=mode_id).get("trusted_sources") or {})
        combined = sort_rag_chunks_by_trusted(list(web_chunks) + list(rag_chunks), trusted, k=8)
    else:
        combined = list(rag_chunks)

    def _fmt_ref(c: RagChunk) -> str:
        meta = c.meta or {}
        src = str(meta.get("source") or "")
        tag = "外搜" if src in ("tavily", "exa") else "RAG"
        dom = str(meta.get("domain") or "")
        url = str(meta.get("source_url") or "")
        head = f"- [{tag}] {c.title} ({c.chunk_id})"
        if dom:
            head += f" domain={dom}"
        if url:
            head += f"\n  url={url}"
        return f"{head}\n{c.content}"

    rag_context_str = "\n\n".join(_fmt_ref(c) for c in combined[:8])
    if not rag_context_str.strip():
        rag_context_str = "（暂无检索上下文）"

    ref_section_title = (
        "参考资料（外搜 + 本地/向量检索，已按 trusted_sources / 可信域加权排序）："
        if is_vision_dept(dept)
        else "参考资料（RAG）："
    )

    xlab_brief = ""
    if dept == "xlab":
        xlab_brief = (
            "你是 X-Lab（破局思考部）。consensus 中请包含：①2–3 个非常规破局假设；"
            "②每个假设的证伪信号/最短验证路径；③若假设不成立时的替代叙事。"
            "conflicts 请写主流方案可能忽略的早期信号或第二类错误。\n"
        )

    llm_text = ""
    parsed = None
    if llm_choice.provider == "litellm":
        # Phase 2: call real model (env-only keys).
        try:
            llm_text = (
                await litellm_client.complete(
                    model=llm_choice.model,
                    fallbacks=llm_router.fallbacks(),
                    prompt=(
                        f"部门={dept}\n"
                        f"{xlab_brief}"
                        f"战术/战略分级={task_level or 'unknown'} 时效={task_urgency or 'unknown'}\n"
                        f"分诊官摘要={dispatcher_notes or '（无）'}\n"
                        f"用户完整任务=\n{task[:4000]}\n\n"
                        f"分诊官下发（仅本部门）=\n{(dispatcher_context or '（无）')[:3500]}\n\n"
                        f"{ref_section_title}\n{rag_context_str}\n\n"
                        "请只输出 JSON（不要输出其它文字），格式如下：\n"
                        "{\n"
                        '  \"consensus\": \"...\",\n'
                        '  \"conflicts\": [\"...\"],\n'
                        '  \"confidence_score\": 0.0,\n'
                        '  \"dissent_intensity\": 0.0\n'
                        "}\n"
                    ),
                )
            ).text
            parsed = parse_dept_output(llm_text)
        except Exception as e:
            llm_text = f"[litellm error] {e!r}"

    raw_debate: list[dict[str, str]] = []
    if dispatcher_context or dispatcher_notes:
        raw_debate.append(
            {
                "role": "Dispatcher",
                "content": (
                    f"[{dept}/Dispatcher] level={task_level} urgency={task_urgency}\n"
                    f"notes={dispatcher_notes}\n"
                    f"{dispatcher_context[:1200] if dispatcher_context else ''}"
                ),
            }
        )
    raw_debate.extend(
        [
        {"role": "System", "content": f"[{dept}/System] llm={llm_choice.provider}:{llm_choice.model} active_gene_prompt={gene_prompt}"},
        {"role": "A", "content": f"[{dept}/A] 保守视角：针对任务《{task[:60]}…》列出主要风险与约束。"},
        {"role": "B", "content": f"[{dept}/B] 进取视角：给出更快更省的路径与可选捷径。"},
        {"role": "C", "content": f"[{dept}/C] 批判视角：逐条攻击 A 与 B 的盲点，指出潜在失败模式。"},
        {
            "role": "Lead",
            "content": f"[{dept}/Lead] 汇总：在风险与收益之间达成一个可执行的折中方案。",
        },
        ]
    )
    if llm_text:
        raw_debate.append({"role": "LLM", "content": llm_text})
    if is_vision_dept(dept):
        raw_debate.append(
            {"role": "ExternalSearch", "content": f"[{dept}/Web] {json.dumps(web_meta, ensure_ascii=False)[:4000]}"}
        )
        cfg = _cfg.get_config(mode_id=mode_id)
        trusted = cfg.get("trusted_sources") or {}
        raw_debate.append({"role": "Policy", "content": f"[{dept}/Policy] trusted_sources={trusted}"})
    if shadow_rec:
        raw_debate.append({"role": "Shadow", "content": f"[{dept}/Shadow] shadow_version={shadow_rec.get('version')} prompt={shadow_prompt}"})

    consensus = f"{dept} 建议：先做 MVP 骨架，保留回滚与审计；再逐步增强。"
    conflicts = [f"{dept} 内部冲突：成本优先 vs 质量优先（MVP 先用模拟）。"]
    if dept == "benchmark":
        cfg = _cfg.get_config(mode_id=mode_id)
        trusted = cfg.get("trusted_sources") or {}
        top = sorted(trusted.items(), key=lambda x: float(x[1]), reverse=True)[:5]
        consensus = f"benchmark 建议：按 trusted_sources 白名单/权重提炼要点（top={top}），并对低可信来源进行权重衰减。"
    elif dept == "xlab":
        consensus = (
            "xlab 建议：列出 3 个与主流假设不同的破局叙事；对每个叙事给出可被数据或实验否定的最短路径；"
            "标注哪些是「赌注」哪些是「对冲」。"
        )

    # If LLM returned parsable JSON, use it as higher-priority signal.
    if parsed is not None:
        consensus = parsed.consensus
        conflicts = parsed.conflicts or conflicts
        confidence = float(parsed.confidence_score)
        dissent = float(parsed.dissent_intensity)

    report = DeptLeadReport(
        dept=dept,  # type: ignore[arg-type]
        consensus=consensus,
        conflicts=conflicts,
        credibility_weight=0.8,
        confidence_score=confidence,
        dissent_intensity=dissent,
        debate_log_id=debate_log_id,
        dispatcher_context=dispatcher_context,
        rag_context=[c.__dict__ for c in combined],
        rag_retrieval_meta=_rag_retrieval_meta(combined, web_chunks),
        raw_debate=raw_debate,
    )

    if shadow_rec and isinstance(shadow_rec.get("version"), int):
        score_active = gene_score(gene_prompt, task)
        score_shadow = gene_score(shadow_prompt, task)
        sv = int(shadow_rec["version"])
        th = hashlib.sha256(task.encode("utf-8")).hexdigest()[:16]
        _shadow.append_score(
            mode_id=mode_id,
            dept=dept,
            shadow_version=sv,
            score_active=score_active,
            score_shadow=score_shadow,
            task_hash=th,
            decision_id=decision_id,
        )
        verdict = _shadow.should_promote(mode_id=mode_id, dept=dept, shadow_version=sv)
        if verdict.promote:
            _genes.set_active(mode_id=mode_id, dept=dept, prompt=shadow_prompt, version=sv)

    bus.publish(
        StreamEvent(
            type="dept_done",
            decision_id=decision_id,
            payload={"dept": dept, "report": report.model_dump()},
        )
    )
    return report


def _alert(confidence: float, dissent: float) -> str:
    if dissent > 0.7 or confidence < 0.5:
        return "red"
    if dissent > 0.4 or confidence < 0.65:
        return "yellow"
    return "green"


def finalize_decision_bundle(
    *,
    decision_id: str,
    task: str,
    mode_id: str,
    mode_label: str,
    dsp_meta: dict[str, Any],
    reports: list[DeptLeadReport],
) -> DecisionSummary:
    """CEO 汇总、执行包、落盘与 decision_done 事件（供 LangGraph finalize 节点与单测复用）。"""
    depts = [r.dept for r in reports]
    heatmap = [
        HeatmapCell(
            dept=r.dept,
            confidence_score=r.confidence_score,
            dissent_intensity=r.dissent_intensity,
            alert=_alert(r.confidence_score, r.dissent_intensity),  # type: ignore[arg-type]
            debate_log_id=r.debate_log_id,
        )
        for r in reports
    ]

    red_depts = [c.dept for c in heatmap if c.alert == "red"]
    lvl = dsp_meta.get("level")
    ceo_decision = f"CEO（分诊：{lvl}）：先完成可运行链路，再按需深化；遵守各部门分诊上下文与热力图预警。"
    if red_depts:
        ceo_decision += f"（预警：{', '.join(red_depts)} 异议/信心触发红色，建议查看原始辩论日志）"

    random.seed(hash(task) % (2**32))
    risks: list[str] = []
    if _stable_float(f"risk:{task}", 0, 1) > 0.55:
        risks.append("红队：注意 API Key 存储与审计日志可能泄露敏感信息，Phase 1 先用 .env + 不落盘。")

    execution = build_execution_bundle(
        expected_depts=depts,
        task=task,
        ceo_decision=ceo_decision,
        dept_reports=list(reports),
        heatmap=heatmap,
    )

    rag_aggregate = compact_rag_hint_from_dept_rows(list(reports))

    summary = DecisionSummary(
        decision_id=decision_id,
        task=task,
        mode_id=mode_id,
        mode_label=mode_label,
        heatmap=heatmap,
        dept_reports=reports,
        ceo_decision=ceo_decision,
        red_team_risks=risks,
        dispatcher=dsp_meta,
        execution=execution,
        rag_aggregate=rag_aggregate,
    )

    bus.publish(StreamEvent(type="decision_done", decision_id=decision_id, payload={"summary": summary.model_dump()}))
    _memory.append_summary(mode_id=mode_id, mode_label=mode_label, summary=summary.model_dump())
    return summary


async def run_decision(*, decision_id: str, task: str, mode_id: str, debate_rounds: int = 1, thinking_frameworks: list[str] | None = None) -> DecisionSummary:
    """决策主链路：LangGraph 三节点编排（dispatcher → 并行部门 → finalize）。"""
    mode = get_mode(mode_id)

    bus.publish(
        StreamEvent(
            type="decision_started",
            decision_id=decision_id,
            payload={"task": task, "mode_id": mode.mode_id, "mode_label": mode.label},
        )
    )

    from .orchestration.decision_graph import invoke_decision_graph

    return await invoke_decision_graph(
        decision_id=decision_id,
        task=task,
        mode_id=mode.mode_id,
        mode_label=mode.label,
        departments=list(mode.departments),
    )

