"""灌书主入口 — 把手写专科书库按 persona 定制灌进 bee-memory.

用法 (在 backend 目录下):
    python -m scripts.seed_knowledge.run_seed family_doctor          # 灌一个场景
    python -m scripts.seed_knowledge.run_seed family_doctor --per 30 # 指定每人本数
    python -m scripts.seed_knowledge.run_seed --all                  # 灌所有已写书库的场景

只灌已经手写了书库的前台场景. 后台 50 extra 场景留懒加载.
"""
from __future__ import annotations

import sys

from .engine import seed_scenario


def _load_libs() -> dict[str, dict]:
    """已手写书库的场景 → {dept_id: SpecialtyLibrary}."""
    libs: dict[str, dict] = {}
    try:
        from .lib_family_doctor import LIBRARIES as fd
        libs["family_doctor"] = fd
    except Exception as e:
        print(f"[warn] family_doctor 书库加载失败: {e!r}")
    # 后续场景书库在这里追加: libs["nutrition_fitness"] = ...
    return libs


def main(argv: list[str]) -> int:
    libs = _load_libs()
    per = 30
    if "--per" in argv:
        i = argv.index("--per")
        try:
            per = int(argv[i + 1])
        except Exception:
            per = 30
        argv = argv[:i] + argv[i + 2:]

    if "--all" in argv:
        targets = list(libs.keys())
    else:
        targets = [a for a in argv[1:] if not a.startswith("--")]
    if not targets:
        print("已写书库的场景:", list(libs.keys()))
        print("用法: python -m scripts.seed_knowledge.run_seed family_doctor [--per 30]")
        return 1

    grand = {"stored": 0, "skipped": 0, "failed": 0, "no_lib": 0, "personas": 0}
    for mode_id in targets:
        if mode_id not in libs:
            print(f"[skip] {mode_id} 还没写书库")
            continue
        print(f"\n=== 灌库: {mode_id} (每人 {per} 本) ===")
        st = seed_scenario(mode_id=mode_id, libraries=libs[mode_id],
                           target_per_persona=per, skip_existing=True, verbose=True)
        for k in grand:
            grand[k] += st.get(k, 0)
        print(f"--- {mode_id}: persona={st['personas']} 灌入={st['stored']} "
              f"跳过={st['skipped']} 失败={st['failed']} 无书库={st['no_lib']}")

    print(f"\n====== 总计: persona={grand['personas']} 灌入={grand['stored']} "
          f"跳过={grand['skipped']} 失败={grand['failed']} ======")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
