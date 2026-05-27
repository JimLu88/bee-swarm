"""Lightweight RAG rollups from persisted dept row shapes (dict or model_dump)."""

from __future__ import annotations

from typing import Any


def compact_rag_hint_from_dept_rows(dept_reports: list[Any]) -> dict[str, Any] | None:
    """
    Aggregate ``rag_retrieval_meta`` across departments.

    Rows may be dicts (JSONL / API) or any object with ``model_dump()`` (e.g. DeptLeadReport).
    Older rows may omit ``rag_retrieval_meta``; ``len(rag_context)`` is used when applicable.
    """
    chunks_sum = 0
    chunks_max_val = 0
    chunks_max_dept: str | None = None
    backends: set[str] = set()
    hybrid_sum = 0
    legacy_chunks_used = False

    def _row_dict(r: Any) -> dict[str, Any]:
        if isinstance(r, dict):
            return r
        md = getattr(r, "model_dump", None)
        if callable(md):
            out = md()
            return out if isinstance(out, dict) else {}
        return {}

    for r in dept_reports:
        row = _row_dict(r)
        meta = row.get("rag_retrieval_meta") if isinstance(row.get("rag_retrieval_meta"), dict) else {}
        tc_ob = meta.get("total_chunks")
        if isinstance(tc_ob, int):
            tc = tc_ob
        else:
            rag_ctx = row.get("rag_context")
            if isinstance(rag_ctx, list):
                tc = len(rag_ctx)
                if tc > 0:
                    legacy_chunks_used = True
            else:
                tc = 0

        chunks_sum += tc
        if tc >= chunks_max_val:
            chunks_max_val = tc
            d = row.get("dept")
            chunks_max_dept = str(d) if d is not None else None

        rb = meta.get("rag_backend")
        if isinstance(rb, str) and rb.strip():
            backends.add(rb.strip())

        ho = meta.get("hybrid_overlap_hits")
        if isinstance(ho, int):
            hybrid_sum += ho

    if chunks_sum == 0 and hybrid_sum == 0 and len(backends) == 0:
        return None

    out: dict[str, Any] = {
        "chunks_sum_across_depts": chunks_sum,
        "max_chunks_in_one_dept": chunks_max_val,
        "hybrid_overlap_sum_across_depts": hybrid_sum,
    }
    if chunks_max_dept:
        out["dept_with_max_chunks"] = chunks_max_dept
    if legacy_chunks_used:
        out["legacy_chunk_counts"] = True
    if len(backends) == 1:
        out["rag_backend"] = next(iter(backends))
    elif len(backends) > 1:
        out["rag_backend"] = "mixed"

    return out
