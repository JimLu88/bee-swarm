"""v6-C 人设知识库检索 — 把人脑式激活 + 8 层知识接入蜂群辩论.

调用链 (decision_engine._run_dept 改后):
  1. 查 team.yaml 找 dept 的 head.persona_id
  2. 调 bee-memory /memory/recall (strategy=activation, persona_id filter)
  3. 拼成 system context 给 LLM, 强制 LLM 引用 [knowledge:<layer>:<id>]
  4. 不调或失败 → 降级到现有 rag/retriever (向后兼容)

6 个防过载机制:
  1. 硬上限 k=10
  2. 层级分配: books×2 cases×3 pitfalls×2 standards×2 history×1
  3. 强制引用: 把 [knowledge_id] 嵌入每条片段头, LLM 必须带回引用
  4. 领域硬隔离: 严格按 persona_id filter
  5. 快照锁定: 一次会诊用一份快照 (在 _run_dept 入口截屏)
  6. 引用统计: 返回的 KnowledgeBundle 含 cited_ids, 决策完成后入 ELO 信号
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field


@dataclass
class KnowledgeFragment:
    """一条知识片段, 含层 + 完整内容 + 唯一 ref_id (LLM 引用用)."""
    ref_id: str           # 形如 "k.book.1" 短引用 ID, 塞 system prompt 让 LLM 引用
    full_id: str          # bee-memory 的真实 memory.id (写 ELO 信号用)
    layer: str            # book / case / pitfall / standard / ...
    title: str
    content: str
    importance: int = 3
    source_url: str = ""


@dataclass
class KnowledgeBundle:
    """一次会诊的知识包 (快照锁定). _run_dept 用它拼 prompt + 收集引用."""
    fragments: list[KnowledgeFragment] = field(default_factory=list)
    snapshot_ts: int = 0
    persona_id: str = ""
    total_chars: int = 0


def retrieve_for_dept(
    *,
    mode_id: str,
    dept_id: str,
    task: str,
    k: int = 10,
) -> KnowledgeBundle:
    """主入口. _run_dept 直接调这个; 失败返回空 bundle (向后兼容)."""
    bundle = KnowledgeBundle(snapshot_ts=int(time.time()))

    try:
        from ..persona.team_store import load_team
        team = load_team(mode_id) or {}
    except Exception:
        return bundle

    persona_id = ""
    for d in team.get("departments") or []:
        if str(d.get("dept_id")) == dept_id:
            head = d.get("head") or {}
            persona_id = str(head.get("persona_id") or "")
            break
    if not persona_id:
        return bundle
    bundle.persona_id = persona_id

    try:
        from ..persona.knowledge_store import recall_for_persona
        raw_items = recall_for_persona(
            mode_id=mode_id,
            persona_id=persona_id,
            query=task,
            k=k,
            strategy="activation",
        )
    except Exception:
        raw_items = []

    for idx, it in enumerate(raw_items[:k]):
        layer = str(it.get("_layer") or "unknown")
        meta = it.get("_meta_parsed") or {}
        ref_id = f"k.{layer[:4]}.{idx + 1}"
        frag = KnowledgeFragment(
            ref_id=ref_id,
            full_id=str(it.get("id") or ""),
            layer=layer,
            title=str(meta.get("title") or layer.upper()),
            content=str(it.get("content") or "")[:1500],
            importance=int(it.get("importance") or 3),
            source_url=str(meta.get("source_url") or ""),
        )
        bundle.fragments.append(frag)
        bundle.total_chars += len(frag.content)

    return bundle


def retrieve_for_ceo(
    *,
    mode_id: str,
    task: str,
    k: int = 12,
) -> KnowledgeBundle:
    """v8: CEO 综合阶段的知识库召回. 按 team.yaml 的 ceo.persona_id 拉 CEO 那 80 本里
    最相关的 k 条 (决策/战略/沟通管理). 失败返回空 bundle (向后兼容)."""
    bundle = KnowledgeBundle(snapshot_ts=int(time.time()))
    try:
        from ..persona.team_store import load_team
        team = load_team(mode_id) or {}
    except Exception:
        return bundle
    ceo = team.get("ceo") or {}
    persona_id = str(ceo.get("persona_id") or "")
    if not persona_id:
        return bundle
    bundle.persona_id = persona_id
    try:
        from ..persona.knowledge_store import recall_for_persona
        raw_items = recall_for_persona(
            mode_id=mode_id, persona_id=persona_id, query=task, k=k, strategy="activation",
        )
    except Exception:
        raw_items = []
    for idx, it in enumerate(raw_items[:k]):
        layer = str(it.get("_layer") or "unknown")
        meta = it.get("_meta_parsed") or {}
        frag = KnowledgeFragment(
            ref_id=f"k.{layer[:4]}.{idx + 1}",
            full_id=str(it.get("id") or ""),
            layer=layer,
            title=str(meta.get("title") or layer.upper()),
            content=str(it.get("content") or "")[:1500],
            importance=int(it.get("importance") or 3),
            source_url=str(meta.get("source_url") or ""),
        )
        bundle.fragments.append(frag)
        bundle.total_chars += len(frag.content)
    return bundle


def format_bundle_for_prompt(bundle: KnowledgeBundle) -> str:
    """格式化成 LLM system context 的一段, 含引用要求."""
    if not bundle.fragments:
        return ""
    parts: list[str] = [
        f"【你的专业知识库 (共 {len(bundle.fragments)} 条片段, 你必须在回答中带 [<ref_id>] 引用每个用到的片段)】",
        "",
    ]
    for f in bundle.fragments:
        head = f"[{f.ref_id}] {f.layer.upper()} · {f.title} (importance={f.importance})"
        if f.source_url:
            head += f" · {f.source_url}"
        parts.append(head)
        parts.append(f.content)
        parts.append("")
    parts.append("规则: 回答 consensus / conflicts 时, 凡是用到了上面片段的论点, "
                 "都要在那句末尾标上对应的 [k.xxx.N] 引用。不依赖片段的纯推理段可以不标。")
    return "\n".join(parts)


def cited_full_ids(bundle: KnowledgeBundle, llm_output: str) -> list[str]:
    """扫 LLM 输出里出现的 [k.xxx.N] 引用, 映射回 bundle.full_id (写 ELO 信号用)."""
    pattern = re.compile(r"\[(k\.[a-z]+\.\d+)\]")
    cited_refs = set(pattern.findall(llm_output))
    return [f.full_id for f in bundle.fragments if f.ref_id in cited_refs and f.full_id]
