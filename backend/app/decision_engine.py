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
# v11: 是否"全力"档 (debate_rounds>=3). 全力才走真·三派 fan-out, 否则走 prompt 版(主管一次调用分饰三派).
_full_power_cv: contextvars.ContextVar[bool] = contextvars.ContextVar("full_power", default=False)

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


def _dining_head_model(dept: str, *, full_power: bool) -> str:
    """v11 餐饮主管模型按比例分配(按 dept 名哈希, 确定性):
    全力档 → 50% opus-4.7 / 50% deepseek-pro; 中档 → 1/3 opus / 2/3 deepseek-pro.
    用强模型给一部分主管把关, 其余用高性价比 pro, 整体质量与成本平衡.
    """
    import os as _os_hd
    opus = "openai/claude-opus-4-7"
    pro = "openai/deepseek-v4-pro"
    bucket = int(hashlib.md5(dept.encode("utf-8")).hexdigest(), 16) % 100
    try:
        _med = max(0, min(100, int(_os_hd.environ.get("BEE_DINING_OPUS_PCT", "50"))))
    except Exception:
        _med = 50
    threshold = 60 if full_power else _med  # 全力 60% opus; 中档默认 50% (env BEE_DINING_OPUS_PCT 可调)
    return opus if bucket < threshold else pro


async def _dining_three_faction_consensus(
    *, dept: str, dept_label: str, task: str, persona_prompt: str,
    kb_context: str, dispatcher_context: str, staff_model: str, head_model: str, fallbacks: list[str],
) -> str:
    """v11 餐饮真·三派 fan-out + 真联网 + 主管(先立场→批判综合).
    学院派(只用书) / 街头派(只用实时联网) / 怀疑派(交叉挑刺) 三 staff 并行,
    主管先立场再逐条采纳/反驳/加强, 综合 8-10 条 + 标分歧. 返回主管的 JSON 文本.
    """
    import asyncio as _aio
    # 街头/怀疑派的真联网素材 (tavily/exa via bee-scraper)
    web_str = "（联网暂无结果）"
    try:
        _chunks, _ = await fetch_benchmark_web_chunks(f"{task} {dept_label} 推荐 店 点评 攻略", limit=4)
        if _chunks:
            parts = []
            for c in _chunks[:4]:
                _u = (c.meta or {}).get("source_url") or ""
                parts.append(f"[{c.title}] {c.content[:500]}" + (f"\n来源: {_u}" if _u else ""))
            web_str = "\n\n".join(parts)
    except Exception:
        pass

    _base = (f"你是「{dept_label}」部门的顾问。用户问题:\n{task[:1500]}\n\n"
             f"蜂枢补充: {(dispatcher_context or '无')[:800]}\n")
    academic_p = (_base + "\n【角色: 学院派】只依据专业知识/书本/原理, 不用实时信息。\n"
                  f"可用书本知识:\n{(kb_context or '（无）')[:2500]}\n\n"
                  "给 8-10 条具体、专业、可落地的建议(每条1-2句, 带原理/依据)。只输出中文要点列表, 不客套。")
    street_p = (_base + "\n【角色: 街头派/实战派】只依据下面实时联网素材+本地经验, 给最新接地气的建议。\n"
                f"联网素材:\n{web_str[:3000]}\n\n"
                "给 8-10 条具体建议, 每条尽量带: 真实店名/地址/人均/必点, 以及可信度评分——"
                "①大众点评评分(如 4.6分/万评) ②TripAdvisor评分(如 4.5/5) ③小红书口碑(约X人推荐, 大致几条说好/几条说踩雷)。"
                "评分查不到就标'(评分待核实)', 不要编。只输出中文要点列表。")
    skeptic_p = (_base + "\n【角色: 怀疑派/风控】交叉比对书本与实时, 专挑要警惕的(卫生/预制/已关店/性价比虚高/信息过时/水军), "
                 "并指出书本说法与现实可能不符之处。\n"
                 f"书本:\n{(kb_context or '（无）')[:1500]}\n实时:\n{web_str[:1500]}\n\n"
                 "给 8-10 条'要小心/要核实'的点。只输出中文要点列表。")

    async def _one(p: str) -> str:
        try:
            return (await litellm_client.complete(model=staff_model, fallbacks=fallbacks, system=persona_prompt, prompt=p)).text or ""
        except Exception as e:
            return f"(该派暂无输出: {e!r})"
    academic, street, skeptic = await _aio.gather(_one(academic_p), _one(street_p), _one(skeptic_p))

    head_p = (
        f"你是「{dept_label}」部门主管。用户问题:\n{task[:1500]}\n\n"
        "① 先用 1-2 句给出你的独立判断(consensus 以「【我的判断】」开头, 别被下属带跑)。\n"
        "你三位下属的意见如下:\n"
        f"=== 学院派(书) ===\n{academic[:2000]}\n\n=== 街头派(实时联网) ===\n{street[:2000]}\n\n=== 怀疑派(风控) ===\n{skeptic[:2000]}\n\n"
        "② 逐条/分组对下属意见表态: 采纳/反驳/加强/补充 + 一句理由(禁止只复述)。\n"
        "③ 综合出你自己的 8-10 条最终建议, 每条标 [书] 或 [实时] 来源 + 适合谁; 会过期的事实(营业/价格/是否还开)末尾标「(需最新核实)」。\n"
        "④ 最后给 conflicts: 三派之间真正的分歧点(每条一句)。\n"
        "consensus 要有干货密度, 禁止一句话敷衍。只输出 JSON:\n"
        '{"consensus":"【我的判断】...(含表态+8-10条建议)","conflicts":["..."],"confidence_score":0.0,"dissent_intensity":0.0}'
    )
    try:
        return (await litellm_client.complete(model=head_model, fallbacks=fallbacks, system=persona_prompt, prompt=head_p)).text or ""
    except Exception as e:
        return f"[head error] {e!r}"


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

    # v6-RAG: 书库向量检索 — 从已灌入的真实书籍 (books_rag: sqlite-vec+FTS5 混合) 召回本场景片段,
    # 与 bee-memory 召回并行注入. 库不存在/无命中则静默跳过, 不影响决策。
    try:
        from .books_rag.pipeline import retrieve_context as _books_ctx
        _bc = _books_ctx(task, scenario=mode_id, k=3)
        if _bc:
            gene_prompt = f"{gene_prompt}\n\n{_bc}"
    except Exception:
        pass

    # v6-RAG #2: 联网实时增强(env BOOKS_WEB_RAG=1 才启用)—— 书库没到位时用实时网络补深度
    try:
        from .books_rag.web_rag import web_context as _web_ctx
        _wc = _web_ctx(task, k=3)
        if _wc:
            gene_prompt = f"{gene_prompt}\n\n{_wc}"
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

    # v9 自学习: 把联网搜索命中写进"知识收件箱", 等 20:00 CEO 梳理入库 (best-effort, 失败不影响决策)
    if web_chunks:
        try:
            from .auto_learning.inbox import record_web_hits
            record_web_hits(
                mode_id=mode_id, dept_id=dept, persona_id=head_persona_id,
                query=rag_query[:500],
                chunks=[c.__dict__ for c in web_chunks],
            )
        except Exception:
            pass

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
    if dept in ("xlab", "out_of_box_breakthrough"):
        xlab_brief = (
            "你是破局思考部（X-Lab / 视野拓展）。consensus 中请包含：①2–3 个非常规破局假设；"
            "②每个假设的证伪信号/最短验证路径；③若假设不成立时的替代叙事。"
            "conflicts 请写主流方案可能忽略的早期信号或第二类错误。\n"
            "【关键: 你必须给「不普通」的选项】其它部门会给常规/主流推荐——你绝不重复他们。"
            "你只给反常规、小众、出人意料但真实可行的选择, 例如(按场景类比): "
            "极端价位的(顶奢/极便宜)、藏在街边巷子的小店/苍蝇馆子、本地人才知道的冷门宝藏、"
            "特色到极致的(单品爆款/主题/手艺人)、逆向玩法(反着来/错峰/跨界组合)。"
            "每条说清「为什么普通人想不到」+「凭什么值得」+「什么人/场合适合」, 宁可大胆也不要四平八稳。\n"
        )
    elif dept == "parallel_architecture_scout":
        xlab_brief = (
            "你是外部平行架构侦察部。任务: 跳出本地/主流信息源, 去找**外部、国外、小众的平替渠道与方案**, "
            "把它们的优质结果带回来。按场景类比: 餐饮别只看大众点评——去翻 TripAdvisor / Google Maps 高分、"
            "米其林/黑珍珠/当地美食博主、外网小众榜单, 找出本地人/常规渠道忽略的高分店; "
            "购物别只看京东淘宝——看 reddit/海淘/海外测评; 学习别只看国内——看 Coursera/YouTube/海外名校公开课。"
            "consensus 必须给**具体的外部来源名 + 它推荐的具体对象(店名/产品/课程等) + 为什么值得借鉴**, "
            "不要泛泛而谈方法论, 更不要谈技术架构。conflicts 写'本地主流渠道与外部渠道结论的差异'。\n"
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

    # v11 餐饮试点: 主管"领导增值"指令 (先立场 + 三派视角 + 8-10点 + 逐条批判 + 知识/实时分流).
    # 仅 dining_recommendation 启用; 满意后推广到其它场景 + 升级为真·三派子智能体 fan-out.
    leader_value_brief = ""
    if mode_id == "dining_recommendation" and dept not in ("xlab", "out_of_box_breakthrough", "parallel_architecture_scout"):
        leader_value_brief = (
            "【主管增值要求·本场景试点 — 务必照做, consensus 要有干货密度, 禁止一句话敷衍】\n"
            "① 先立场: 看任何资料前, 先凭你的专业判断写 1-2 句初步主张, 放在 consensus 开头, 以「【我的判断】」起头。\n"
            "② 三派视角: 给出共 8-10 条具体建议, 每条标来源标签 [书/理论] 或 [实时/外部] + 适合谁/什么场合, 覆盖三个视角:\n"
            "   · 学院派: 菜系源流 / 食材 / 正统做法 / 搭配原理;\n"
            "   · 街头派: 本地人排队的店 / 实时点评 / 外网小众榜单(给具体店名+地址+人均+必点+评分: 大众点评分/TripAdvisor/小众书约N人推荐口碑);\n"
            "   · 怀疑派: 卫生口碑 / 是否预制菜 / 是否已关店或搬迁 / 性价比是否虚高 等要警惕的点。\n"
            "③ 批判: 对三派之间的分歧逐条表态(我采纳/我反驳/我加强 + 一句理由), 不要只罗列。\n"
            "④ 知识 vs 实时: 凡'会过期的事实'(营业时间/价格/是否还开)末尾标「(需最新核实)」。\n"
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
    # v11 餐饮: 仅"全力"档(debate_rounds>=3)走真·三派 fan-out; 日常档(简单/一般/深入)走 prompt 版(下方单调用 + leader_value_brief).
    import os as _os_dr
    _dining_base = (
        mode_id == "dining_recommendation"
        and dept not in ("xlab", "out_of_box_breakthrough", "parallel_architecture_scout")
        and llm_choice.provider == "litellm"
    )
    _full = _full_power_cv.get(False)
    _dining_real = _dining_base and _full
    if _dining_base and not _full:
        # 中档 prompt 版: 主管按 1/3 opus · 2/3 deepseek-pro 分配
        _effective_model = _dining_head_model(dept, full_power=False)
    if _dining_real:
        # 全力档真·三派: staff 用便宜快的 flash; 主管按 50% opus · 50% pro 分配 (可 env 覆盖).
        _staff_model = _os_dr.environ.get("BEE_DINING_STAFF_MODEL", "openai/deepseek-v4-flash")
        _head_model = _os_dr.environ.get("BEE_DINING_HEAD_MODEL", "") or _dining_head_model(dept, full_power=True)
        try:
            from .modes import get_mode as _gm2
            _dlabel = (getattr(_gm2(mode_id), "department_labels", {}) or {}).get(dept, dept)
            llm_text = await _dining_three_faction_consensus(
                dept=dept, dept_label=_dlabel, task=task, persona_prompt=gene_prompt,
                kb_context=rag_context_str, dispatcher_context=dispatcher_context,
                staff_model=_staff_model, head_model=_head_model, fallbacks=llm_router.fallbacks(),
            )
            parsed = parse_dept_output(llm_text)
        except Exception as e:
            llm_text = f"[dining 3-faction error] {e!r}"
    elif llm_choice.provider == "litellm":
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
                        f"{leader_value_brief}"
                        f"{xlab_brief}"
                        f"{differential_brief}"
                        f"{framework_brief}"
                        f"战术/战略分级={task_level or 'unknown'} 时效={task_urgency or 'unknown'}\n"
                        f"蜂枢摘要={dispatcher_notes or '（无）'}\n"
                        f"用户完整任务=\n{task[:4000]}\n\n"
                        f"蜂枢下发（仅本部门）=\n{(dispatcher_context or '（无）')[:3500]}\n\n"
                        f"{ref_section_title}\n{rag_context_str}\n\n"
                        f"可用工具(可选, 不需要也行):\n{tools_brief}\n\n"
                        "【输出铁律】consensus 必须是你作为本领域专家、针对用户问题给出的"
                        "直接、具体、可落地的答案本身(真实的名称/地点/做法/数字/步骤), 像当面回答客户。"
                        "【篇幅要够】consensus 至少 500 字: 把每个推荐项展开讲透——具体名称/地址/人均/"
                        "必点或关键做法/为什么/适合谁/什么场合, 给足干货密度, 严禁一两句话敷衍了事。"
                        "严禁任何过程性元话语——不要提'我的人设/RAG/知识库匹不匹配/要不要调用工具/"
                        "任务是否命中关键词/本部门职责'这类内部机制, 用户只看结论。"
                        "conflicts 可留空, 或一句话点出你与主流看法的关键不同即可"
                        "(跨部门的真正分歧由 CEO 统一提炼, 这里不必展开、不要凑泛泛对立)。\n"
                        "请只输出 JSON, 格式如下:\n"
                        "{\n"
                        '  "consensus": "直接给具体答案本身, 不要写任何过程/机制的话",\n'
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
        kb_used=(len(kb_bundle.fragments) if kb_bundle is not None else 0),
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
            "注意: 这是你个人专科意见, 最终由蜂枢(CEO)综合取舍; 但你这里绝不能因为'可能性小'就省略不写。\n"
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
    # v9 部门 id → 中文 (红队预警/展示用, 含横切部门), 避免 CEO 文末出现英文 dept id
    try:
        from .modes import get_mode as _gm, CROSSCUTTING_DEPT_LABELS as _cc
        _dept_cn = {**_cc, **(getattr(_gm(mode_id), "department_labels", {}) or {})}
    except Exception:
        _dept_cn = {}

    def _dcn(d: str) -> str:
        return str(_dept_cn.get(d, d)).split(" (")[0].split("（")[0]

    red_depts_cn = [_dcn(d) for d in red_depts]
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
            # v6-RAG: CEO 也接书库向量检索 (跨部门真书), 追加到知识段
            try:
                from .books_rag.pipeline import retrieve_context as _books_ctx
                _ceo_books = _books_ctx(task, scenario=mode_id, k=4)
                if _ceo_books:
                    ceo_kb_section = f"{ceo_kb_section}\n\n{_ceo_books}" if ceo_kb_section else _ceo_books
            except Exception:
                pass
            # v6-RAG #2: CEO 也接联网实时增强(env 开关)
            try:
                from .books_rag.web_rag import web_context as _web_ctx
                _ceo_web = _web_ctx(task, k=4)
                if _ceo_web:
                    ceo_kb_section = f"{ceo_kb_section}\n\n{_ceo_web}" if ceo_kb_section else _ceo_web
            except Exception:
                pass
            # v11 餐饮试点: CEO 富输出 — 不当转发员, 必须加入自己的判断 (1️⃣先立场 + 2️⃣逐条批判 + 结构化富输出).
            if mode_id == "dining_recommendation":
                ceo_output_spec = (
                    "【CEO 最终输出·本场景 — 你不是转发员, 必须加入你自己的判断, 中文 markdown, 内容要充实详尽(宁长勿短)】\n"
                    "严格按以下顺序输出, **把最重要的结论放最前面**, 让用户一眼看到核心:\n\n"
                    "## 一句话钦定\n先用 1 句给出你作为决策者的最终主张(今天就去哪/怎么选)。\n\n"
                    "## 总研判(放最前面)\n把所有建议直接分三档, 让用户秒懂:\n"
                    "  - 🟢 强烈推荐: 3-5 个, 每个一行=名称 + 一句为什么 + **评分**(优先用上面「真实高德 POI 评分/人均」, 标来源「高德」; 高德没有的标「(评分待核实)」, 小红书/网络口碑作补充, 不要编)\n"
                    "  - 🟡 可选(看场景): 每个一句话点评 + 评分\n"
                    "  - 🔴 不建议: 每个一句话说清为什么别去\n\n"
                    "## 推荐方向详解 (5-8 条)\n每条 = 具体建议(店名/地址/人均/必点) + 为什么 + 适合谁/什么场合 + **三平台评分**(点评/TripAdvisor/小红书口碑: 约N人推荐、几条好评几条说踩雷); 其中至少 2-3 条要'不普通'(冷门/特色/反常规)。\n\n"
                    "## 我对各部门的研判\n对部门建议逐条/分组表态——采纳/反驳/加强/补充 + 一句理由(禁止只复述)。\n\n"
                    "## ⚖ 关键分歧\n只写部门之间**真正互相矛盾**的点(如 A 部门力荐某店、B 部门说别去, 或"
                    "'图便宜实惠'vs'重体验氛围'的实质对立), 并给出你的裁决与理由。没有真冲突就写"
                    "'各部门方向一致, 无重大分歧'。**不要罗列泛泛的'成本vs质量'套话。**\n\n"
                    "## 补充(部门没提但重要的)\n1-3 点。\n\n"
                    "## ⚠ 风险避雷 (3-5 条)\n踩雷店/预制菜/性价比虚高/排队/卫生/已关店等。\n\n"
                    "评分查不到标'(评分待核实)'不要编; 会过期的事实(营业/价格)标「(需最新核实)」。要有干货密度和你的主观判断, 不要流水账。\n"
                )
            else:
                ceo_output_spec = (
                    "现在按上面 SOP, 直接输出最终回答 (中文, markdown 可用).\n"
                    "- 若部门意见一致 → 综合成一段\n"
                    "- ⚖ 关键分歧: 若部门之间有真正互相矛盾的主张, 单列一段点明并给你的裁决; 无真冲突则不写此段 (不要凑泛泛对立)\n"
                    "- 红队风险单独最后一段 ⚠ 标出 (无风险则省略此段)\n"
                )
            # v13 #2 长期记忆: 注入用户画像 (让 CEO 认识你, 建议更贴合; 关开关/为空则不注入)
            try:
                from .user_profile import format_for_prompt as _fmt_profile
                _user_profile_block = _fmt_profile()
            except Exception:
                _user_profile_block = ""
            # v3 餐饮/地点真实评分: CEO 综合前取高德 POI 评分/人均注入, 让 CEO 按真分排序而非编造 (best-effort)
            _amap_ratings_block = ""
            try:
                from .geocoder import GEO_SCENES as _geo_scenes, gather_ratings_brief as _grb
                if mode_id in _geo_scenes:
                    from .media_aggregator import gather_media_cards as _gmc_pre
                    _pre_cards = await _gmc_pre(task, mode_id, decision_id=decision_id)  # 命中缓存, 不重爬
                    _amap_ratings_block = await _grb(mode_id=mode_id, media_cards=_pre_cards)
            except Exception:
                _amap_ratings_block = ""
            # v? 技能复用: 把 p3 蒸馏的历史 SOP 中命中当前任务的注入 CEO, 闭合"沉淀→复用"回路 (best-effort)
            _skills_block = ""
            try:
                from .skills_store import match_skills as _msk, format_skills_brief as _fsk
                _skills_block = _fsk(_msk(task, mode_id, k=3))
            except Exception:
                _skills_block = ""
            ceo_prompt = (
                (sop_section + "\n---\n\n" if sop_section else "")
                + (ceo_framework_brief + "\n" if ceo_framework_brief else "")
                + (ceo_kb_section + "\n---\n\n" if ceo_kb_section else "")
                + (_user_profile_block + "\n" if _user_profile_block else "")
                + f"用户任务: {task}\n\n"
                + f"以下是 {len(reports)} 个部门的独立意见:\n\n{dept_views}\n\n"
                + (_amap_ratings_block + "\n\n" if _amap_ratings_block else "")
                + (_skills_block + "\n\n" if _skills_block else "")
                + ceo_output_spec
            )
            # v13 复杂题 (算账/比合同/多步推导) → 切推理模型, 原 CEO 模型留作 fallback (失败自动退回).
            _ceo_model = ceo_choice.model
            _ceo_fallbacks = llm_router.fallbacks()
            try:
                from .llm.router import reasoning_model_for as _rmf
                _reasoning = _rmf(task)
                if _reasoning:
                    _ceo_model = _reasoning
                    _ceo_fallbacks = [ceo_choice.model] + _ceo_fallbacks
            except Exception:
                pass
            ceo_text = (await litellm_client.complete(
                model=_ceo_model,
                fallbacks=_ceo_fallbacks,
                prompt=ceo_prompt,
            )).text or ""
            ceo_decision = ceo_text.strip()
    except Exception as _e:
        ceo_decision = f"[CEO LLM 综合失败: {_e!r}]"

    if not ceo_decision:
        ceo_decision = f"CEO（分诊：{lvl}）：先完成可运行链路，再按需深化；遵守各部门分诊上下文与热力图预警。"
    if red_depts:
        ceo_decision += f"\n\n⚠ 注意:{', '.join(red_depts_cn)} 部门有红色预警,可展开看详情。"

    # v13 #2 决策后异步提炼用户画像 (fire-and-forget, 不给主链路加延迟; 关了开关自动跳过)
    try:
        from . import user_profile as _up
        _up.store_async(task, ceo_decision)
    except Exception:
        pass

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
        risks.append(f"{red_depts_cn[0]} 部门有较大异议或信心较低, 建议你看下原始意见再决定.")

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
        media_cards = await gather_media_cards(task, mode_id, decision_id=decision_id)
    except Exception:
        media_cards = []

    # v12 信源可信度 + 观点权重 (先覆盖 12 个前台场景): 给卡片打 credibility + 汇总 consensus.
    # best-effort: 非前台场景/失败 → media_cards 原样, consensus={}.
    source_consensus: dict[str, Any] = {}
    try:
        from .source_credibility import analyze_credibility
        _cred = await analyze_credibility(task, mode_id, media_cards)
        media_cards = _cred.get("cards", media_cards)
        source_consensus = _cred.get("consensus") or {}
    except Exception:
        source_consensus = {}

    # v11 方案4 地图钉店: 抽店名 → 高德地理编码 → 坐标 (best-effort; 仅带地点场景+配了 AMAP_KEY).
    map_places: list[dict[str, Any]] = []
    try:
        from .geocoder import gather_map_places
        map_places = await gather_map_places(mode_id=mode_id, ceo_text=ceo_decision, media_cards=media_cards)
    except Exception:
        map_places = []

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
        map_places=map_places,
        source_consensus=source_consensus,
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

    # 群晖/无 GPU 部署: HSEMAS_DISABLE_LOCAL_TIER=1 时, C 档(本地 ollama) 自动降级到 B 档便宜云.
    if tier == "C":
        import os as _os
        if _os.environ.get("HSEMAS_DISABLE_LOCAL_TIER", "0") == "1":
            tier = "B"

    # v8: 把用户显式选的思维框架放进 contextvar, 供 _run_dept/finalize 注入 prompt;
    # 空列表时 _run_dept 会按 task 关键词自动选 (trigger_keywords).
    _active_frameworks.set(list(thinking_frameworks or []))
    _full_power_cv.set(int(debate_rounds or 1) >= 3)  # 全力档(3轮) → 真·三派; 其余 → prompt 版

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

    # v13 #1 第②步: 决策前实时资料采集 (MCP 工具). best-effort, 失败/未配置自动跳过.
    # 把天气/股价/网页/文献等实时结果拼进 task, 所有部门+CEO 共享 (env HSEMAS_MCP_FACTS=0 关).
    try:
        from . import mcp_orchestrator
        mcp_facts, mcp_calls = await mcp_orchestrator.gather_facts(mode_id=mode.mode_id, task=task)
        if mcp_facts:
            task = f"{task}\n\n{mcp_facts}"
            bus.publish(StreamEvent(
                type="mcp_facts",
                decision_id=decision_id,
                payload={"calls": [{"server": c.get("server"), "tool": c.get("tool"),
                                     "ok": c.get("ok")} for c in (mcp_calls or [])]},
            ))
    except Exception as _mcp_e:
        bus.publish(StreamEvent(
            type="mcp_facts_error", decision_id=decision_id, payload={"error": repr(_mcp_e)},
        ))

    # v14: 决策前实时候选采集 (联网+爬虫). 拼进 task 让所有部门+CEO 共享同一批真实资料
    # (答案与图文瀑布/大屏同源, 解决"图文与回答脱节"); 按 decision_id 缓存供 finalize 复用, 不重复爬. best-effort.
    try:
        from .media_aggregator import gather_media_cards as _gmc, candidates_digest as _cdg
        _cands = await _gmc(task, mode.mode_id, decision_id=decision_id)
        _dg = _cdg(_cands)
        if _dg:
            task = f"{task}\n\n{_dg}"
        bus.publish(StreamEvent(
            type="live_candidates", decision_id=decision_id, payload={"count": len(_cands)},
        ))
    except Exception as _ce:
        bus.publish(StreamEvent(
            type="live_candidates_error", decision_id=decision_id, payload={"error": repr(_ce)},
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

