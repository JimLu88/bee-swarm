from __future__ import annotations

import asyncio
import contextvars
import hashlib
import json
import random
import time
import uuid
from typing import Any

from .thinking_frameworks import build_framework_brief

# v8 思维框架: run_decision 把用户显式选的框架放进 contextvar, _run_dept/finalize 读出来;
# 没显式选则按 task 关键词自动选 (见 thinking_frameworks.select_framework_ids).
_active_frameworks: contextvars.ContextVar[list[str]] = contextvars.ContextVar(
    "active_frameworks", default=[]
)

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
from .tools import extract_tool_calls, execute_tool, list_tools as list_bee_tools


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
    tier: str = "A",
    images: list[str] | None = None,
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

    # v6-A: team.yaml override — 如果该 mode 有 AI 生成的 team, 用 head 的 prompt 和 model 取代 gene
    head_persona_id: str = ""
    team_head_vendor: str = ""
    try:
        from .persona.team_store import load_team as _load_team_yaml
        _team = _load_team_yaml(mode_id)
        if _team:
            _dept_entry = next(
                (d for d in (_team.get("departments") or []) if str(d.get("dept_id")) == dept),
                None,
            )
            if _dept_entry:
                _head = _dept_entry.get("head") or {}
                _head_prompt = str(_head.get("prompt") or "").strip()
                # v6-W 按档取模型: tier A/B/C → model_modeA/B/C
                _tier_field = f"model_mode{tier}"
                _head_model = str(_head.get(_tier_field) or _head.get("model_modeA") or "").strip()
                if _head_prompt:
                    gene_prompt = _head_prompt   # 真用 head 的 system prompt
                if _head_model and llm_choice.provider == "litellm":
                    from .llm.router import LLMChoice as _LLMChoice
                    llm_choice = _LLMChoice(provider="litellm", model=_head_model)
                head_persona_id = str(_head.get("persona_id") or "")
                team_head_vendor = str(_head.get("model_vendor") or "")
    except Exception:
        pass

    # v6-C: 人设知识库 — 调 bee-memory /memory/recall (strategy=activation) 拉 top-10 知识片段,
    # 拼到 system prompt 让 head 引用. v3-D 6 因子激活 + 2 跳沿边扩散在这一步真正生效。
    kb_bundle = None
    kb_context = ""
    if head_persona_id:
        try:
            from .rag.persona_kb_retriever import retrieve_for_dept, format_bundle_for_prompt
            kb_bundle = retrieve_for_dept(mode_id=mode_id, dept_id=dept, task=task, k=10)
            if kb_bundle.fragments:
                kb_context = format_bundle_for_prompt(kb_bundle)
                gene_prompt = f"{gene_prompt}\n\n{kb_context}"
        except Exception:
            pass

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

    # v8: 按场景注入"列全本专科可能性"要求 (避免各部门只挑最相关的说, 漏掉低概率可能).
    differential_brief = build_differential_brief(mode_id, dept)

    # v8: 思维框架 (第一性原理/逆向/六顶帽 等) 真注入. 用户显式选优先, 否则按 task 关键词自动选.
    framework_brief = build_framework_brief(task, _active_frameworks.get() or None)

    # v6-D 真工具: 把 BeeServiceClient 工具清单露给 LLM, 让它可选择性 tool_calls
    bee_tools_safe = list_bee_tools(include_sensitive=False)
    tools_brief = "\n".join(
        f"  - {t['name']}({', '.join(t['args_schema'].keys())}) : {t['description']}"
        for t in bee_tools_safe
    )

    llm_text = ""
    parsed = None
    # v6-X 多模态预处理: 有图但 model 瞎 → 查 vision_fallback 表换视觉兄弟.
    # 注意: image_summary 已在 dispatcher_context 里 (decision_graph 拼好), staff 不需要原图也能"读到".
    # 只有 head 才需要原图详细看; 这里 _run_dept 是 head 视角, 所以传原图.
    _imgs = list(images or [])
    _effective_model = llm_choice.model
    _vision_swapped = False
    if _imgs and llm_choice.provider == "litellm":
        from .llm.vision_capability import swap_for_vision
        _effective_model, _vision_swapped = swap_for_vision(llm_choice.model)
        if _vision_swapped:
            bus.publish(StreamEvent(
                type="vision_model_swapped",
                decision_id=decision_id,
                payload={"dept": dept, "from": llm_choice.model, "to": _effective_model},
            ))
    if llm_choice.provider == "litellm":
        # Phase 2: call real model (env-only keys).
        try:
            llm_text = (
                await litellm_client.complete(
                    model=_effective_model,
                    fallbacks=llm_router.fallbacks(),
                    system=gene_prompt,
                    images=_imgs if _imgs else None,
                    prompt=(
                        f"部门={dept}\n"
                        f"{xlab_brief}"
                        f"{differential_brief}"
                        f"{framework_brief}"
                        f"战术/战略分级={task_level or 'unknown'} 时效={task_urgency or 'unknown'}\n"
                        f"分诊官摘要={dispatcher_notes or '（无）'}\n"
                        f"用户完整任务=\n{task[:4000]}\n\n"
                        f"分诊官下发（仅本部门）=\n{(dispatcher_context or '（无）')[:3500]}\n\n"
                        f"{ref_section_title}\n{rag_context_str}\n\n"
                        f"可用工具(可选, 不需要也行):\n{tools_brief}\n\n"
                        "请只输出 JSON, 格式如下:\n"
                        "{\n"
                        '  "consensus": "...",\n'
                        '  "conflicts": ["..."],\n'
                        '  "confidence_score": 0.0,\n'
                        '  "dissent_intensity": 0.0,\n'
                        '  "tool_calls": [   // 可选, 想用工具就填; 最多 3 个\n'
                        '     {"tool": "scrape", "args": {"site":"hacker_news","limit":5}}\n'
                        '  ]\n'
                        "}\n"
                    ),
                )
            ).text
            parsed = parse_dept_output(llm_text)
        except Exception as e:
            llm_text = f"[litellm error] {e!r}"

    # v6-D 真工具调用: 解析 tool_calls 并真执行 (safe 才自动跑, sensitive 显式跳过)
    tool_results: list[dict[str, Any]] = []
    for call in extract_tool_calls(llm_text)[:3]:
        tool_results.append(execute_tool(call["tool"], call.get("args") or {},
                                         allow_sensitive=False))

    raw_debate: list[dict[str, str]] = []
    # v6-C: 记录 LLM 引用了哪些 KB 片段 (写演化日志 + 后续 ELO 信号)
    if kb_bundle is not None and kb_bundle.fragments and llm_text:
        try:
            from .rag.persona_kb_retriever import cited_full_ids
            cited = cited_full_ids(kb_bundle, llm_text)
            if cited:
                raw_debate.append({
                    "role": "KB_Citations",
                    "content": (
                        f"[{dept}/KB] persona={kb_bundle.persona_id} "
                        f"frags_loaded={len(kb_bundle.fragments)} "
                        f"cited={cited[:20]}"
                    ),
                })
        except Exception:
            pass

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
        {"role": "System", "content": f"[{dept}/System] llm={llm_choice.provider}:{_effective_model if llm_choice.provider == 'litellm' else llm_choice.model}{' (vision-swapped from ' + llm_choice.model + ')' if _vision_swapped else ''} head_persona={head_persona_id or '(gene)'} vendor={team_head_vendor or '-'} images={len(_imgs)} active_gene_prompt={gene_prompt[:600]}"},
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

    # v6-D 工具结果回灌 (每个 tool_call 单独一行, 截断到 1500 字防爆)
    for tr in tool_results:
        body = (tr.get("result") if tr.get("ok") else tr.get("error")) or {}
        body_str = json.dumps(body, ensure_ascii=False, default=str) \
            if not isinstance(body, str) else body
        raw_debate.append({
            "role": "Tool",
            "content": (
                f"[{dept}/Tool] name={tr.get('tool')} "
                f"ok={tr.get('ok')} safety={tr.get('safety','-')}\n"
                f"args={json.dumps(tr.get('args') or {}, ensure_ascii=False)[:600]}\n"
                f"out={body_str[:1500]}"
            ),
        })
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
    else:
        # v6-W-fix 最后兜底: LLM 真返回了内容但既不是JSON也救不回 → 直接拿原文当 consensus,
        # 绝不用"MVP 骨架"占位符盖掉真实意见 (那正是之前 11 部门全一样的根因).
        _txt = (llm_text or "").strip()
        _is_err = (not _txt) or _txt.startswith("[litellm") or _txt.startswith("[simulated")
        if not _is_err and llm_choice.provider == "litellm":
            # 去掉可能的 ```json 包裹残留
            _clean = _txt.strip("`").lstrip("json").strip()
            consensus = _clean[:2000]
            conflicts = []
            raw_debate.append({
                "role": "ParseNote",
                "content": f"[{dept}/解析] LLM 未输出规范JSON, 已直接采用其原文作为意见 (len={len(_txt)})。",
            })

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


# v8: 鉴别诊断/全可能性要求 — 按场景定制 (医疗强制全列, 其它轻量, 避免啰嗦).
# 医疗类: 每个专科必须列出本专科所有可能引起该症状的病因 (含低概率), 标可能性高/中/低.
_MEDICAL_MODES = {"family_doctor", "chronic_disease", "health_checkup"}
# 其它"需要穷举可能性"的专业场景 (轻量提示)
_DIFFERENTIAL_MODES = {
    "legal_consulting", "tax_insurance", "stock_trading",
    "purchase_decision", "startup_advisory",
}


def build_differential_brief(mode_id: str, dept: str) -> str:
    """返回注入 prompt 的"列全本专科可能性"要求. 不适用场景返回空串."""
    if mode_id in _MEDICAL_MODES:
        return (
            "【鉴别诊断要求 (本专科必做)】你必须站在本专科角度, 列出**所有**可能引起"
            "患者症状的本专科病因——哪怕概率很低、哪怕本次主诉看起来不像本专科问题, "
            "只要本专科有可能解释该症状, 就要列出。每条标注可能性 [高/中/低] + 一句依据/排除点。"
            "consensus 里设一个'本专科鉴别诊断清单'段落完整列出。"
            "注意: 这是你个人专科意见, 最终由分诊官(CEO)综合取舍; 但你这里绝不能因为'可能性小'就省略不写。\n"
        )
    if mode_id in _DIFFERENTIAL_MODES:
        return (
            "【穷举要求】请从本部门专业角度, 把所有相关的可能性/风险/选项都列出来 (含小概率但有影响的), "
            "每条标注重要性 [高/中/低]。宁可多列, 由 CEO 最后取舍, 不要因为'可能性小'就漏掉。\n"
        )
    return ""


def _alert(confidence: float, dissent: float) -> str:
    if dissent > 0.7 or confidence < 0.5:
        return "red"
    if dissent > 0.4 or confidence < 0.65:
        return "yellow"
    return "green"


async def finalize_decision_bundle(
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

    # v1.2 真 LLM 综合 CEO 决策 (失败回退到模板兜底)
    ceo_decision = ""
    try:
        from .llm.router import router as _ceo_router
        ceo_choice = _ceo_router.pick_for_dept("ceo") if hasattr(_ceo_router, "pick_for_dept") else None
        if ceo_choice and getattr(ceo_choice, "provider", "") == "litellm":
            dept_views = "\n\n".join(
                f"[{r.dept}] {r.consensus}" + (f"\n冲突: {'; '.join(r.conflicts)}" if r.conflicts else "")
                for r in reports
            )
            # v6-J 从 ceo_sop.yaml 读 SOP, 拼成 system prompt
            sop_section = ""
            try:
                import yaml as _yaml_ceo
                from pathlib import Path as _P_ceo
                sop_path = _P_ceo(__file__).resolve().parent / "prompts" / "ceo_sop.yaml"
                if sop_path.is_file():
                    sop = _yaml_ceo.safe_load(sop_path.read_text(encoding="utf-8")) or {}
                    role = sop.get("role", "").strip()
                    principles = sop.get("principles", []) or []
                    steps = sop.get("steps", []) or []
                    qc = sop.get("quality_checklist", []) or []
                    sop_section = (
                        f"## 你的角色\n{role}\n\n"
                        f"## 6 条原则\n" +
                        "\n".join(f"- {p}" for p in principles) + "\n\n"
                        f"## 5 步法 (内化, 不要把步骤名写进输出)\n" +
                        "\n".join(f"{i+1}. **{s.get('name')}**: {s.get('purpose')}\n   {s.get('internal_prompt','').strip()}"
                                  for i, s in enumerate(steps)) + "\n\n"
                        f"## 自检清单 (输出前心里过一遍)\n" +
                        "\n".join(f"- {q}" for q in qc) + "\n"
                    )
            except Exception:
                sop_section = ""

            ceo_framework_brief = build_framework_brief(task, _active_frameworks.get() or None)
            # v8: CEO 综合阶段也召回知识库 (CEO 那 80 本: 决策/战略/沟通管理), 之前完全没接.
            ceo_kb_section = ""
            try:
                from .rag.persona_kb_retriever import retrieve_for_ceo, format_bundle_for_prompt as _fmt_kb
                _ceo_bundle = retrieve_for_ceo(mode_id=mode_id, task=task, k=12)
                ceo_kb_section = _fmt_kb(_ceo_bundle)
            except Exception:
                ceo_kb_section = ""
            ceo_prompt = (
                (sop_section + "\n---\n\n" if sop_section else "")
                + (ceo_framework_brief + "\n" if ceo_framework_brief else "")
                + (ceo_kb_section + "\n---\n\n" if ceo_kb_section else "")
                + f"用户任务: {task}\n\n"
                + f"以下是 {len(reports)} 个部门的独立意见:\n\n{dept_views}\n\n"
                + "现在按上面 SOP, 直接输出最终回答 (中文, markdown 可用).\n"
                + "- 若部门意见一致 → 综合成一段\n"
                + "- 若有重要冲突 → 指出冲突并给推荐方案 (附 1-2 句理由)\n"
                + "- 红队风险单独最后一段 ⚠ 标出 (无风险则省略此段)\n"
            )
            ceo_text = (await litellm_client.complete(
                model=ceo_choice.model,
                fallbacks=llm_router.fallbacks(),
                prompt=ceo_prompt,
            )).text or ""
            ceo_decision = ceo_text.strip()
    except Exception as _e:
        ceo_decision = f"[CEO LLM 综合失败: {_e!r}]"

    if not ceo_decision:
        ceo_decision = f"CEO（分诊：{lvl}）：先完成可运行链路，再按需深化；遵守各部门分诊上下文与热力图预警。"
    if red_depts:
        ceo_decision += f"\n\n⚠ 注意:{', '.join(red_depts)} 部门有红色预警,可展开看详情。"

    # v1.2 红队风险 — 真 LLM 分析任务 + 部门意见, 失败兜底
    risks: list[str] = []
    try:
        from .llm.router import router as _risk_router
        risk_choice = _risk_router.pick_for_dept("ceo") if hasattr(_risk_router, "pick_for_dept") else None
        if risk_choice and getattr(risk_choice, "provider", "") == "litellm":
            dept_views_short = "\n".join(
                f"[{r.dept}] {r.consensus[:200]}" for r in reports
            )
            risk_prompt = (
                f"用户任务: {task}\n\n"
                f"部门意见摘要:\n{dept_views_short}\n\n"
                "扮演红队 (Red Team) 提出最值得用户警惕的 1-3 个风险点 (按重要度排序). "
                "每个 risk 一行, 简短直接, 中文. 不要赘述, 不要客套, 不要 markdown. "
                "如果实在没有重大风险, 输出空行即可."
            )
            risk_text = (await litellm_client.complete(
                model=risk_choice.model,
                fallbacks=llm_router.fallbacks(),
                prompt=risk_prompt,
            )).text or ""
            for ln in risk_text.splitlines():
                ln2 = ln.strip().lstrip("- *0123456789. ")
                if len(ln2) > 8:
                    risks.append(ln2[:300])
            risks = risks[:3]
    except Exception:
        pass
    # 实在没产出: 看是否有红色预警部门, 给个通用提示
    if not risks and red_depts:
        risks.append(f"{red_depts[0]} 部门有较大异议或信心较低, 建议你看下原始意见再决定.")

    execution = build_execution_bundle(
        expected_depts=depts,
        task=task,
        ceo_decision=ceo_decision,
        dept_reports=list(reports),
        heatmap=heatmap,
    )

    rag_aggregate = compact_rag_hint_from_dept_rows(list(reports))

    # v8 信息流: 聚合爬虫/web 搜索结果成 media_cards 给前端 InfoFeed (best-effort, 失败返回 []).
    media_cards: list[dict[str, Any]] = []
    try:
        from .media_aggregator import gather_media_cards
        media_cards = await gather_media_cards(task, mode_id)
    except Exception:
        media_cards = []

    # v6-B ELO 信号: 从 team.yaml 提取本次决策实际用了的 head + staff
    team_personas_used: list[dict[str, Any]] = []
    try:
        from .persona.team_store import load_team as _load_team
        _team = _load_team(mode_id) or {}
        active_depts = {str(r.dept) for r in reports}
        for d in _team.get("departments") or []:
            did = str(d.get("dept_id"))
            if did not in active_depts:
                continue
            head = d.get("head") or {}
            if head.get("persona_id"):
                team_personas_used.append({
                    "persona_id": head["persona_id"], "role": "head",
                    "model": head.get("model_modeA", ""), "dept_id": did,
                })
            for s in d.get("staff") or []:
                if s.get("persona_id"):
                    team_personas_used.append({
                        "persona_id": s["persona_id"], "role": "staff",
                        "model": s.get("model_modeA", ""), "dept_id": did,
                    })
        ceo_p = _team.get("ceo") or {}
        if ceo_p.get("persona_id"):
            team_personas_used.append({
                "persona_id": ceo_p["persona_id"], "role": "ceo",
                "model": ceo_p.get("model_modeA", ""), "dept_id": "__ceo__",
            })
    except Exception:
        pass

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
        team_personas_used=team_personas_used,
        media_cards=media_cards,
    )

    bus.publish(StreamEvent(type="decision_done", decision_id=decision_id, payload={"summary": summary.model_dump()}))
    _memory.append_summary(mode_id=mode_id, mode_label=mode_label, summary=summary.model_dump())
    return summary


import asyncio as _asyncio_v6w
# v6-W 本地档 (tier=C) 同时只跑 2 个 dept (ollama 单实例并发弱; 防止排队过载)
_LOCAL_TIER_SEMAPHORE = _asyncio_v6w.Semaphore(2)


async def build_image_summary(*, images: list[str], tier: str, task: str) -> str:
    """v6-X-5 一次性图像摘要: 用最便宜的视觉模型把图变成纯文字, 后续所有 staff/瞎子模型读这段文字.

    省钱原理: 9 head × 27 staff = 36 次调用, 如果每次都发图, 成本爆炸.
    改成 vision 跑 1 次 (~¥0.05), 输出 600 字摘要, 后续全部读文字 (0 额外图成本).

    Args:
        images: data URL / https URL 列表 (1-4 张)
        tier: A/B/C, 决定用哪个摘要模型 (gemini-flash / doubao / llava:7b)
        task: 用户任务 — 让摘要"按任务相关"重点描述图, 不浪费 token 说无关细节

    Returns: 纯文字描述 (失败时返回 "[图像摘要失败: ...]")
    """
    if not images:
        return ""
    from .llm.vision_capability import image_summary_model
    vmodel = image_summary_model(tier)
    summary_prompt = (
        f"用户提了个问题: {task[:400]}\n\n"
        f"请只看图, 用 300-600 字客观描述图里的关键信息 (与上面问题相关的). "
        f"按列表输出, 不要分析、不要建议、不要诊断, 只描述事实. "
        f"如果图里有文字/数字/图表数据, 完整列出. 多张图分别编号 (图1/图2/...)."
    )
    try:
        resp = await litellm_client.complete(
            model=vmodel,
            system="你是医疗/数据/财务图像的客观描述员, 只描述看到什么, 不下判断.",
            prompt=summary_prompt,
            images=images,
        )
        return (resp.text or "").strip() or "[图像摘要为空]"
    except Exception as e:
        return f"[图像摘要失败 model={vmodel} err={e!r}]"


# v6-Z CEO 预分析用的便宜模型 (deepseek-flash; fallback 链里有 opus 兜底)
_PREFLIGHT_MODEL = "openai/deepseek-v4-flash"


async def ceo_preflight(*, task: str, mode_id: str, images: list[str] | None = None,
                        files: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """v6-Z CEO 预分析: 便宜 LLM 读任务 → 推荐启动哪些部门 + 路线 + 轮数.

    返回结构 (供前端 5 路线 × 3 轮数 选择器):
    {
      mode_id, mode_label,
      all_depts: [...], all_labels: {id:label},
      multi_depts: [...], key_depts: [...], single_dept: "...",
      reasoning: "CEO 的一句话分析",
      ceo_recommended_route, ceo_recommended_rounds_band,
      sop: {recommended_route, recommended_rounds_band, recommended_rounds, explored, arms},
      difficulty,
      recommended_route, recommended_rounds_band  # 最终默认高亮(SOP 优先, 无数据则用 CEO)
    }
    """
    from .llm.parsing import _extract_json
    from . import sop_bandit
    from .dispatcher import classify_task

    mode = get_mode(mode_id)
    all_depts = list(mode.departments)
    labels = dict(getattr(mode, "department_labels", {}) or {})

    # 难度桶
    meta = classify_task(task)
    difficulty = sop_bandit.difficulty_bucket(task, str(meta.get("level") or ""))

    # 文件名/张数给 CEO 做路由判断 (不需要看图细节, 只需知道"有附件")
    attach_note = ""
    if files:
        names = ", ".join(str(f.get("name") or "?") for f in files)
        attach_note += f"\n[用户附了 {len(files)} 个文档: {names}]"
    if images:
        attach_note += f"\n[用户附了 {len(images)} 张图片]"

    # CEO 读历史 SOP 偏好 (软参考; 让 CEO 慢慢靠拢历史好评选择, 但不强制 — 配合 5% 探索防僵化)
    try:
        sop_history = sop_bandit.summary_for_sop(mode_id)
    except Exception:
        sop_history = ""

    dept_menu = "\n".join(f"  - {d}: {labels.get(d, d)}" for d in all_depts)
    sys_prompt = (
        f"你是「{mode.label}」场景的会诊总指挥 (CEO). 用户提了个任务, 你要快速判断该启动哪些专科部门.\n"
        f"可用部门菜单:\n{dept_menu}\n\n"
        + (f"{sop_history}\n(以上是历史统计, 当软参考: 倾向但别盲从, 任务确实不同就大胆换路线)\n\n" if sop_history else "")
        + "只输出 JSON, 不要解释. 格式:\n"
        "{\n"
        '  "key_depts": ["最关键的2-3个部门id"],\n'
        '  "multi_depts": ["相关的4-7个部门id"],\n'
        '  "single_dept": "最相关的1个部门id",\n'
        '  "reasoning": "一句话(40字内)说明为什么这样分",\n'
        '  "recommended_route": "all|multi|key|single|ceo_only",\n'
        '  "recommended_rounds_band": "heavy|medium|light"\n'
        "}\n"
        "判断原则: 简单/单一领域→single或ceo_only+light; 多领域交叉→multi+medium; "
        "高风险/不可逆/复杂权衡→key或all+heavy. 部门id必须来自菜单."
    )
    user_prompt = f"用户任务:\n{task[:2000]}{attach_note}"

    llm_obj: dict[str, Any] = {}
    llm_err = ""
    try:
        resp = await litellm_client.complete(
            model=_PREFLIGHT_MODEL,
            fallbacks=llm_router.fallbacks(),
            system=sys_prompt,
            prompt=user_prompt,
        )
        llm_obj = _extract_json(resp.text or "") or {}
    except Exception as e:
        llm_err = repr(e)

    def _valid(ids: Any) -> list[str]:
        if not isinstance(ids, list):
            return []
        return [str(x) for x in ids if str(x) in all_depts]

    key_depts = _valid(llm_obj.get("key_depts")) or all_depts[:3]
    multi_depts = _valid(llm_obj.get("multi_depts")) or all_depts[: min(6, len(all_depts))]
    single_raw = str(llm_obj.get("single_dept") or "")
    single_dept = single_raw if single_raw in all_depts else (key_depts[0] if key_depts else all_depts[0])
    reasoning = str(llm_obj.get("reasoning") or "").strip() or (
        f"(预分析模型未返回, {llm_err or '已用默认分组'})"
    )
    ceo_route = str(llm_obj.get("recommended_route") or "")
    if ceo_route not in sop_bandit.ROUTES:
        ceo_route = "multi"
    ceo_band = str(llm_obj.get("recommended_rounds_band") or "")
    if ceo_band not in sop_bandit.ROUNDS_BANDS:
        ceo_band = "medium"

    # SOP 学到的偏好 (Thompson 采样 + 5% 探索)
    sop = sop_bandit.recommend(mode_id, difficulty)
    # 最终默认高亮: 若该难度桶有历史样本则用 SOP, 否则用 CEO 当前判断
    has_history = any(v.get("n", 0) > 0 for v in sop.get("arms", {}).values())
    final_route = sop["recommended_route"] if has_history else ceo_route
    final_band = sop["recommended_rounds_band"] if has_history else ceo_band

    return {
        "mode_id": mode_id,
        "mode_label": mode.label,
        "all_depts": all_depts,
        "all_labels": labels,
        "multi_depts": multi_depts,
        "key_depts": key_depts,
        "single_dept": single_dept,
        "reasoning": reasoning,
        "ceo_recommended_route": ceo_route,
        "ceo_recommended_rounds_band": ceo_band,
        "sop": sop,
        "sop_has_history": has_history,
        "difficulty": difficulty,
        "recommended_route": final_route,
        "recommended_rounds_band": final_band,
        "llm_error": llm_err,
    }


async def run_decision(*, decision_id: str, task: str, mode_id: str, debate_rounds: int = 1, thinking_frameworks: list[str] | None = None, tier: str = "A", images: list[str] | None = None, files: list[dict[str, Any]] | None = None, route: str = "all", departments_override: list[str] | None = None) -> DecisionSummary:
    """决策主链路：LangGraph 三节点编排（dispatcher → 并行部门 → finalize）.

    v6-W: tier=A 高档旗舰 / B 便宜云 / C 本地 ollama (限并发 2)
    v6-X: images 传给 triage 节点 → 一次性 vision 摘要 → staff 读文字; head 收原图.
    v6-Y: files (xlsx/pdf/docx...) 进程内解析成文字, prepend 到 task, 所有部门/所有模型免费可读.
    v6-Z: route 决定跑哪些部门 — all=全部 / multi|key|single=部门子集(departments_override) / ceo_only=不跑部门直接CEO答.
    """
    mode = get_mode(mode_id)

    # v8: 把用户显式选的思维框架放进 contextvar, 供 _run_dept/finalize 注入 prompt;
    # 空列表时 _run_dept 会按 task 关键词自动选 (trigger_keywords).
    _active_frameworks.set(list(thinking_frameworks or []))

    # v6-Y 文档附件: 解析成文字拼到 task 前面 (内部 task 字符串无 20k 限制).
    if files:
        try:
            from .file_extract import extract_files
            file_block = extract_files(files)
            if file_block:
                task = f"{file_block}\n\n[用户的问题]\n{task}"
                bus.publish(StreamEvent(
                    type="files_parsed",
                    decision_id=decision_id,
                    payload={"file_count": len(files), "chars": len(file_block)},
                ))
        except Exception as e:
            bus.publish(StreamEvent(
                type="files_parse_error",
                decision_id=decision_id,
                payload={"error": repr(e)},
            ))

    bus.publish(
        StreamEvent(
            type="decision_started",
            decision_id=decision_id,
            payload={"task": task, "mode_id": mode.mode_id, "mode_label": mode.label},
        )
    )

    from .orchestration.decision_graph import invoke_decision_graph

    # v6-Z 路线决定基础部门集合
    route = (route or "all").lower()
    valid_override = [d for d in (departments_override or []) if d in mode.departments]
    if route == "ceo_only":
        departments = []                       # 不跑任何部门, CEO 直接基于任务作答
    elif route in ("multi", "key", "single") and valid_override:
        departments = list(valid_override)     # 用前端/CEO 选定的子集
        if route == "single":
            departments = departments[:1]
    else:
        departments = list(mode.departments)   # all (或子集为空时兜底全开)

    # v6-I 视野拓展部强制注入 (env BEE_DISABLE_VISION_EXPANSION=1 可关).
    # ceo_only / single 跳过 (轻量路线不该被强行加 2 个横切部门).
    import os as _os_vi
    if departments and route not in ("ceo_only", "single") and \
            _os_vi.environ.get("BEE_DISABLE_VISION_EXPANSION", "0") != "1":
        from .persona.team_generator import VISION_EXPANSION_DEPTS
        for d in VISION_EXPANSION_DEPTS:
            if d not in departments:
                departments.append(d)

    bus.publish(StreamEvent(
        type="route_resolved",
        decision_id=decision_id,
        payload={"route": route, "departments": departments, "count": len(departments), "rounds": debate_rounds},
    ))

    # v6-Z ceo_only: 不跑部门, 直接让 CEO 基于任务(+附件摘要)作答.
    # 走 finalize_decision_bundle(reports=[]) 而非 LangGraph (空 fan-out 会让 deferred finalize 不触发).
    if route == "ceo_only":
        image_summary = ""
        if images:
            image_summary = await build_image_summary(images=list(images), tier=tier, task=task)
            if image_summary:
                task = f"{task}\n\n[用户上传图片摘要]\n{image_summary}"
        bus.publish(StreamEvent(
            type="dispatcher_ready", decision_id=decision_id,
            payload={"level": "ceo_only", "note": "CEO 单独作答 (未启动部门)"},
        ))
        return await finalize_decision_bundle(
            decision_id=decision_id,
            task=task,
            mode_id=mode.mode_id,
            mode_label=mode.label,
            dsp_meta={"level": "ceo_only", "department_count": 0, "route": "ceo_only"},
            reports=[],
        )

    return await invoke_decision_graph(
        decision_id=decision_id,
        task=task,
        mode_id=mode.mode_id,
        mode_label=mode.label,
        departments=departments,
        debate_rounds=debate_rounds,
        tier=tier,
        images=list(images or []),
    )

