from __future__ import annotations

from .modes import get_mode


def build_initial_gene_prompt(mode_id: str, dept: str) -> str:
    """Default active gene when none exists on disk — merges YAML ``gene_seeds`` for this dept."""
    mode = get_mode(mode_id)
    base = f"你是 {dept} 部门的 Lead。请给出可执行建议，并输出 confidence_score 与 dissent_intensity。"
    seed = (mode.gene_seeds or {}).get(dept, "")
    seed = str(seed).strip()
    if seed:
        return f"{base}\n\n【场景模板补充】\n{seed}"
    return base
