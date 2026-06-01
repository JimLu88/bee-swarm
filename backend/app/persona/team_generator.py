"""v6-A LLM 团队生成器 — Opus 调研 + 设计部门 + 匹配主管 + 写 prompt.

流程:
  1. 读 model_capabilities.yaml (10 家 Tier-1 旗舰快照)
  2. 给 Opus 一次性 prompt: "调研当前可用的 6 家旗舰 → 为这个场景设计部门 → 匹配主管 → 给每人写 prompt"
  3. 强制 JSON 输出, 严格 schema
  4. 返回 dict, 由 team_store.save_team 持久化

模型可用性: 如果某家旗舰对应的 LiteLLM 路由名 (api_id) 在 hub_settings 里没配 key,
team 写入后 'missing_api_keys' 字段会带告警 (不自动 fallback)。
"""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

import yaml

from ..llm.litellm_client import litellm_client
from ..settings_llm_rag import llm_rag_settings
from ..modes import get_mode

CAPS_PATH = Path(__file__).resolve().parent / "model_capabilities.yaml"
# v6 修脱节 #3: 默认改 DeepSeek 省钱 (从 Opus ¥15-20 → DeepSeek ¥0.5-1).
# v6-Q 修召集 502: 优先用用户在 设置 里配的"主用 AI 大脑" (走 LiteLLM 网关);
# env 显式 BEE_GENERATOR_MODEL 仍能覆盖; 最后才 fallback 到 deepseek.
import os as _os


def _hub_or_instance_get(field: str) -> str:
    """v6-U 优先读 hub_settings.json (UI 实时配置), 兜底读 settings_llm_rag 实例 (.env)."""
    try:
        from ..hub_settings_store import load_hub_file
        hub = load_hub_file() or {}
        v = str(hub.get(field) or "").strip()
        if v:
            return v
    except Exception:
        pass
    try:
        from ..settings_llm_rag import llm_rag_settings as _s
        return str(getattr(_s, field, None) or "").strip()
    except Exception:
        return ""


def _resolve_ceo_model() -> str:
    env = _os.environ.get("BEE_GENERATOR_MODEL", "").strip()
    if env:
        return env
    v = _hub_or_instance_get("litellm_default_model")
    return v or "deepseek/deepseek-chat"


def _resolve_ceo_fallback() -> str:
    env = _os.environ.get("BEE_GENERATOR_FALLBACK", "").strip()
    if env:
        return env
    fb = _hub_or_instance_get("litellm_fallback_models")
    if fb:
        return fb.split(",")[0].strip()
    return _resolve_ceo_model()


# v6-U2 模型家族匹配关键词 (主模型挂时, fallback 优先同族同档次)
_FAMILY_KEYWORDS = [
    ("opus", "claude-opus"),       # claude-opus-4-7 → claude-opus-4-6
    ("sonnet", "claude-sonnet"),   # claude-sonnet-4-7 → claude-sonnet-4-6
    ("haiku", "claude-haiku"),
    ("gpt-5", "gpt-5"),
    ("gpt-4", "gpt-4"),
    ("gemini-3", "gemini-3"),
    ("gemini-2", "gemini-2"),
    ("grok-4", "grok-4"),
    ("deepseek-v4", "deepseek-v4"),
    ("kimi-k2", "kimi-k2"),
    ("qwen3", "qwen3"),
]


def _smart_fallback_for(primary: str) -> list[str]:
    """v6-U2 智能 fallback: 主模型挂了, 优先用同家族同档次的备用 (4.7 → 4.6).

    比 fallback 到差太多的小模型 (deepseek-v4-flash) 更稳: 团队设计需要旗舰水平,
    fallback 到小模型 JSON schema 都填不全, 还是失败.
    """
    primary_lower = primary.lower()
    fb_chain_raw = _hub_or_instance_get("litellm_fallback_models")
    fb_chain = [m.strip() for m in fb_chain_raw.split(",") if m.strip()]
    fb_chain = [m for m in fb_chain if m != primary]

    # 1) 优先找同家族
    for kw, _ in _FAMILY_KEYWORDS:
        if kw in primary_lower:
            for m in fb_chain:
                if kw in m.lower():
                    return [m]  # 只返 1 个, 不要再 chain (防时长叠加)

    # 2) 找不到同族, 用备用链第一个
    if fb_chain:
        return [fb_chain[0]]
    return []


def _ceo_model_now() -> str:
    return _resolve_ceo_model()


def _ceo_fallback_now() -> str:
    return _resolve_ceo_fallback()


# 启动期取一次 (写 yaml 默认值时用); 调用 LLM 时改用 _ceo_model_now() 重算
CEO_DEFAULT_MODEL = _resolve_ceo_model()
CEO_FALLBACK = _resolve_ceo_fallback()


def _load_capabilities() -> dict[str, Any]:
    try:
        return yaml.safe_load(CAPS_PATH.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def _user_default_is_openai_gateway() -> bool:
    """v6-U 判断用户配的主用 AI 大脑是否走 openai 兼容网关 (shiyunapi 等).
    优先读 hub_settings.json (UI 配置, 实时), 兜底 settings_llm_rag (.env 默认值).
    """
    try:
        from ..hub_settings_store import load_hub_file
        hub = load_hub_file() or {}
        v = str(hub.get("litellm_default_model") or "").strip()
        if v:
            return v.startswith("openai/")
    except Exception:
        pass
    try:
        from ..settings_llm_rag import llm_rag_settings as _s
        return (_s.litellm_default_model or "").startswith("openai/")
    except Exception:
        return False


def _load_keys_from_hub() -> dict[str, Any]:
    """v6-U 读 hub_settings.json 拿真实的 *_api_key 字段 (旧 get_provider_keys 不存在, 导致永远空 dict)."""
    out: dict[str, Any] = {}
    try:
        from ..hub_settings_store import load_hub_file
        out.update(load_hub_file() or {})
    except Exception:
        pass
    # 兜底再读 settings_llm_rag (.env / 启动期注入)
    try:
        from ..settings_llm_rag import llm_rag_settings as _s
        for field in ("anthropic_api_key", "openai_api_key", "deepseek_api_key",
                      "gemini_api_key", "doubao_api_key"):
            if not out.get(field):
                v = getattr(_s, field, None)
                if v:
                    out[field] = v
    except Exception:
        pass
    return out


def _has_key_for(api_id: str) -> bool:
    keys = _load_keys_from_hub()
    prefix = api_id.split("/", 1)[0].lower()
    key_map = {
        "anthropic": "anthropic_api_key",
        "openai": "openai_api_key",
        "deepseek": "deepseek_api_key",
        "gemini": "gemini_api_key",
        "mistral": "mistral_api_key",
        "moonshot": "moonshot_api_key",
        "meta-llama": "together_api_key",
    }
    k = key_map.get(prefix)
    if k is None:
        return True
    if keys.get(k):
        return True
    # v6-U 兜底: 走 openai 兼容网关 (shiyunapi 等) 时, openai key 通就视为所有 vendor 都通
    if keys.get("openai_api_key") and _user_default_is_openai_gateway():
        return True
    return False


# v6-U 用户走 openai 兼容网关时, native vendor 前缀全部改写成 openai/ 走聚合
_NATIVE_PREFIXES_TO_REWRITE = (
    "anthropic/", "gemini/", "deepseek/", "mistral/", "moonshot/", "meta-llama/"
)


def _normalize_to_user_gateway(api_id: str | None) -> str | None:
    if not api_id or api_id.startswith("ollama/"):
        return api_id
    if not _user_default_is_openai_gateway():
        return api_id
    for p in _NATIVE_PREFIXES_TO_REWRITE:
        if api_id.startswith(p):
            return "openai/" + api_id[len(p):]
    return api_id


def _patch_team_to_user_gateway(team: dict[str, Any]) -> None:
    """把 team 内所有 model_modeA/B 改写成走用户网关 (防 anthropic/... 直走 native 报 502)."""
    def _patch(p: dict[str, Any] | None) -> None:
        if not p:
            return
        for k in ("model_modeA", "model_modeB"):
            v = p.get(k)
            if v:
                p[k] = _normalize_to_user_gateway(str(v))
    _patch(team.get("ceo"))
    for d in (team.get("departments") or []):
        _patch(d.get("head"))
        for s in (d.get("staff") or []):
            _patch(s)


def _user_model_chain_hint() -> str:
    """返回用户实际配置的模型链, 当作 prompt 上下文喂给 LLM, 防 LLM 写出用户没配的型号."""
    try:
        from ..settings_llm_rag import llm_rag_settings as _s
        primary = (_s.litellm_default_model or "").strip()
        fallbacks = [m.strip() for m in (_s.litellm_fallback_models or "").split(",") if m.strip()]
    except Exception:
        return ""
    if not primary and not fallbacks:
        return ""
    lines = ["## v6-U 用户当前实际配置的模型链 (★ model_modeA/B 必须只从这里挑, 写其它型号会 502 ★)",
             f"主用大脑 (CEO/重要 head 用): {primary}"]
    if fallbacks:
        lines.append("备用 / 候选 head 模型 (按优先级):")
        for i, m in enumerate(fallbacks[:12], 1):
            lines.append(f"  {i}. {m}")
    lines.append("staff 一律用 ollama_chat/qwen2.5:7b-instruct (本地, 免费)")
    return "\n".join(lines)


def _missing_keys_warning(team: dict[str, Any]) -> list[str]:
    used_models: set[str] = set()
    ceo = team.get("ceo") or {}
    for k in ("model_modeA", "model_modeB"):
        if ceo.get(k):
            used_models.add(str(ceo[k]))
    for d in team.get("departments") or []:
        for src in (d.get("head") or {},) + tuple(d.get("staff") or []):
            for k in ("model_modeA", "model_modeB"):
                if src.get(k):
                    used_models.add(str(src[k]))
    missing: list[str] = []
    for m in used_models:
        if m.startswith("ollama/"):
            continue
        if not _has_key_for(m):
            missing.append(m)
    return sorted(missing)


def _try_parse_json(text: str) -> dict[str, Any] | None:
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t
        if t.endswith("```"):
            t = t.rsplit("```", 1)[0]
        t = t.strip()
    try:
        return json.loads(t)
    except Exception:
        start = t.find("{")
        end = t.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(t[start:end + 1])
            except Exception:
                return None
    return None


def _assign_persona_ids(team: dict[str, Any], mode_id: str) -> dict[str, Any]:
    seen: set[str] = set()

    def _unique(prefix: str) -> str:
        base = prefix or f"p_{uuid.uuid4().hex[:6]}"
        cand = base
        i = 1
        while cand in seen:
            cand = f"{base}_{i}"
            i += 1
        seen.add(cand)
        return cand

    ceo = team.get("ceo") or {}
    ceo["persona_id"] = _unique(str(ceo.get("persona_id") or f"ceo_{mode_id}"))
    team["ceo"] = ceo
    for d in team.get("departments") or []:
        d_id = str(d.get("dept_id", "dept"))
        head = d.get("head") or {}
        head["persona_id"] = _unique(str(head.get("persona_id") or f"head_{d_id}"))
        d["head"] = head
        for i, s in enumerate(d.get("staff") or []):
            s["persona_id"] = _unique(str(s.get("persona_id") or f"staff_{d_id}_{i}"))
    return team


def _load_function_templates_summary() -> str:
    """v3-B 真接入: 把 6 个职能模板的标题 + 核心方法浓缩列给 Opus."""
    tpl_dir = Path(__file__).resolve().parent / "function_templates"
    if not tpl_dir.exists():
        return ""
    lines: list[str] = []
    for f in sorted(tpl_dir.glob("*.yaml")):
        try:
            d = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        except Exception:
            continue
        name = d.get("name") or d.get("id") or f.stem
        sp = str(d.get("system_prompt") or "")[:200].replace("\n", " ")
        ocean = d.get("ocean_traits") or {}
        lines.append(f"- **{name}** | OCEAN: O={ocean.get('openness', '?')} C={ocean.get('conscientiousness', '?')} E={ocean.get('extraversion', '?')} A={ocean.get('agreeableness', '?')} N={ocean.get('neuroticism', '?')} | 核心: {sp}")
    return "\n".join(lines)


# v6-E 推荐角色池: LLM 在生成 staff 时可参考这些角色 (针对代码/业务类场景特别有用).
# 不是必填; LLM 看到后按场景采用. dispatcher 也可根据关键词建议哪些必须有.
RECOMMENDED_ROLES_LIBRARY = {
    "user_tester": {
        "title": "用户测试员",
        "best_for": ["code_development", "product_design", "ux_review"],
        "specialty": "代表真实用户; 不懂技术细节, 关注'我能不能用、好不好懂、坑在哪'",
        "ocean_hint": "高 A (随和), 高 N (敏感, 容易发现别扭), 中 O",
        "prompt_seed": (
            "你扮演一个【完全不懂技术的真实用户】, 第一次拿到这个产品/方案. "
            "你的任务: 找出哪些步骤会卡住、哪些文案看不懂、哪些情况会让人弃用. "
            "用第一人称口语化吐槽, 不要给技术建议. 真用户怎么说就怎么说."
        ),
    },
    "qa_engineer": {
        "title": "专业测试员",
        "best_for": ["code_development", "system_review"],
        "specialty": "QA 工程师 / 测试架构师; 关注边界 case、异常路径、性能与并发",
        "ocean_hint": "极高 C (严谨), 高 O (爱挖坑), 低 A (敢质疑)",
        "prompt_seed": (
            "你是专业 QA 工程师. 收到方案/代码后: 1) 列出至少 10 个可能失败的边界场景; "
            "2) 给出可执行的测试用例 (输入/期望/边界); 3) 标出潜在性能/并发/安全雷区. "
            "不写实现代码; 只输出测试矩阵 + 风险清单."
        ),
    },
    "code_reviewer_optimizer": {
        "title": "代码审查优化员",
        "best_for": ["code_development"],
        "specialty": "资深工程师; 看到 PR/代码后做: 精简冗余 + 性能优化 + 可维护性",
        "ocean_hint": "极高 C, 高 O, 中 A (建设性批评)",
        "prompt_seed": (
            "你是资深代码审查工程师. 收到代码后: 1) 标出冗余/重复/可合并的段; "
            "2) 指出明显的性能问题 (算法复杂度/内存/IO); 3) 给出更精简的等价写法 (含 diff). "
            "原则: 在不改变行为前提下, 让代码尽可能短 + 快 + 易读."
        ),
    },
    "business_researcher": {
        "title": "业务研究员",
        "best_for": ["business_research", "startup_advisory", "marketing_strategy"],
        "specialty": "深度业务调研; 比如小红书运营 (养号/起号/对抗风控/合规边界)",
        "ocean_hint": "高 O (好奇), 高 C (体系化), 中 E",
        "prompt_seed": (
            "你是资深业务研究员, 像麦肯锡分析师 + 实操运营高手的结合. "
            "收到一个业务话题 (如'小红书推广系统'): 1) 拆解业务全链路 (用户/平台/流量/变现); "
            "2) 列出关键玩法 + 风控边界 + 合规红线; 3) 引用真实案例数据 (有出处); "
            "4) 输出结构化研究报告 (问题/现状/玩法/风险/建议). 不空想, 不喊口号."
        ),
    },
    # v6-I 视野拓展部 (每场景必备, 由 dispatcher 强制注入)
    "parallel_architecture_scout": {
        "title": "外部平行架构对比员",
        "best_for": ["*"],
        "specialty": "扫描全球同类系统/方案/产品, 横向对比给本场景'借鉴清单'",
        "ocean_hint": "高 O (极开放), 中 C, 中 E",
        "prompt_seed": (
            "你是外部平行架构侦察员. 收到任意话题, 立刻: "
            "1) 列出全球 3-5 个'解决类似问题的现成方案' (产品/库/方法论, 含 URL); "
            "2) 横向对比: 它们怎么做、为什么这么做、有什么坑; "
            "3) 抽取 2-3 个可被本场景借鉴的具体设计; "
            "4) 标注'我们要不要抄/改/避'. 不空谈, 给具体的人/项目/数据."
        ),
    },
    "out_of_box_breakthrough": {
        "title": "破局思考员",
        "best_for": ["*"],
        "specialty": "Think out of the box; 完全不同的视角假设/最短证伪路径",
        "ocean_hint": "极高 O, 低 C (容错乱想), 高 N",
        "prompt_seed": (
            "你是破局思考员, 专门反主流叙事. 收到问题后: "
            "1) 列 3 个与主流方案完全相反的'破局假设' (e.g. '其实根本不需要 X' / '反过来做 Y'); "
            "2) 每个假设给一个最短的证伪路径 (1 周内能验证); "
            "3) 如果证伪了就回归主流; 如果证不伪就大赌一把; "
            "4) 标注'赌注/对冲'比例. 鼓励疯狂, 但每个都要有可测试钩子."
        ),
    },
}

# v6-I dispatcher 强制注入的部门 id (即使现 mode.departments 没列, 也加进 fanout)
VISION_EXPANSION_DEPTS = ("parallel_architecture_scout", "out_of_box_breakthrough")


def _build_prompt(mode_id: str, scenario_label: str, dept_list: list[tuple[str, str]],
                  capabilities: dict[str, Any]) -> str:
    caps_yaml = yaml.safe_dump(capabilities, allow_unicode=True, sort_keys=False)
    depts_md = "\n".join(f"  - {dept_id}  ({label})" for dept_id, label in dept_list)
    templates_md = _load_function_templates_summary()
    # v6-E: 角色池 (按场景关键词智能匹配; 出现在 dept_list 标签里就推荐)
    recommended_roles_md = ""
    label_text = " ".join(label for _, label in dept_list).lower() + " " + mode_id.lower()
    matched = []
    for role_id, role in RECOMMENDED_ROLES_LIBRARY.items():
        if any(kw in label_text for kw in role["best_for"]) or any(
            tag in label_text for tag in ("代码", "开发", "测试", "code", "dev", "qa", "业务", "运营", "research", "marketing", "startup")
        ):
            matched.append(f"  - **{role['title']}** ({role_id}): {role['specialty']}\n    OCEAN 倾向: {role['ocean_hint']}\n    prompt 起点: {role['prompt_seed'][:150]}…")
    if matched:
        recommended_roles_md = (
            "\n## v6-E 推荐角色池 (本场景可能用得上, 按需采用)\n"
            + "\n".join(matched) + "\n"
        )
    user_chain = _user_model_chain_hint()
    return f"""你是 H-SEMAS 蜂群系统的【团队架构师】。基于下面的真实模型行情, 为这个场景设计一支完整的多学科团队。{recommended_roles_md}

{user_chain}

## 场景
- mode_id: {mode_id}
- 标签: {scenario_label}

## 部门列表 (已固定, 不要改 dept_id, 但你可以改 label 让它符合实际)
{depts_md}

## 全球 Tier-1 旗舰模型行情快照 (能力参考, 但 ★ model_modeA/B 必须从上面用户的模型链里挑 ★)
```yaml
{caps_yaml}
```

## v3-B 备选职能方法论模板 (你为每个 head 选 1 个作为方法论底色)
{templates_md or '(无)'}

不要直接 copy 上面的 prompt 原文, 而是**融入**到该 head 的方法论部分, 并尽量让 head.ocean 跟模板推荐的 OCEAN 接近。

## 你的任务
1. **CEO**: 选 Opus 4.7 当 CEO, 给写 system prompt (300-500 字), 含: 综合各部门意见, 主持多学科会诊, 拒绝乱编, 对用户负责
2. **每个部门**:
   - 配 1 个 **head** (部门主管 / 主任医师 / 总师), 从快照里挑**最适合该部门特色的旗舰** (例: 影像类用 Gemini, 中文专科用 DeepSeek, 法律用 Kimi)
   - 配 **3 个 staff** (职员 / 主治 / 助手), 全部用 `ollama_chat/qwen2.5:7b-instruct` 走本地
   - 每个角色都要有: 名字 + 头衔 + sub_specialty (子专业) + ocean (五维 0-1 浮点) + personality + diagnostic_style + 完整 system prompt (200-400 字)
3. **多样性**: head 之间用**不同公司**的模型, 不要全 Opus; staff 之间用不同 OCEAN 分布

## 输出 strict JSON (无 markdown, 无注释), schema:
{{
  "ceo": {{
    "persona_id": "ceo_<short>",
    "name": "<姓+职务>",
    "title": "<会诊主席/总师>",
    "model_modeA": "anthropic/claude-opus-4-7",
    "model_modeB": "anthropic/claude-opus-4-7",
    "prompt": "<完整 system prompt>"
  }},
  "departments": [
    {{
      "dept_id": "<现有 dept_id, 不要改>",
      "label": "<可以改成更贴该场景的中文名>",
      "head": {{
        "persona_id": "head_<short>",
        "name": "<姓+主任>",
        "title": "<主任医师/首席工程师>",
        "sub_specialty": "<具体专科子方向>",
        "ocean": {{"O": 0.6, "C": 0.85, "E": 0.55, "A": 0.5, "N": 0.3}},
        "personality": "<2-3 句性格描述>",
        "diagnostic_style": "<诊断/分析方法论>",
        "model_modeA": "<某家旗舰 api_id, 见快照>",
        "model_modeB": "<升级用旗舰 api_id, 通常同 modeA 或 Opus>",
        "model_vendor": "<对应公司名>",
        "prompt": "<200-400 字 system prompt>"
      }},
      "staff": [
        {{
          "persona_id": "staff_<short>",
          "name": "<姓+职位>",
          "title": "<主治/助手>",
          "sub_specialty": "<>",
          "ocean": {{"O": ..., "C": ..., "E": ..., "A": ..., "N": ...}},
          "personality": "<>",
          "diagnostic_style": "<>",
          "model_modeA": "ollama_chat/qwen2.5:7b-instruct",
          "model_modeB": "anthropic/claude-haiku-4-5",
          "prompt": "<200-400 字 system prompt>"
        }}
      ]
    }}
  ]
}}

只输出 JSON, 不要任何额外文字或 markdown 围栏。
"""


async def generate_full_team(mode_id: str) -> dict[str, Any]:
    """一次性生成整个团队 (CEO + N 个部门 head + staff). 耗时约 30-90 秒, 成本 ~¥3."""
    import logging as _logging
    _log = _logging.getLogger("bee.team_generator")

    mode = get_mode(mode_id)
    caps = _load_capabilities()
    dept_list = [(d, mode.department_labels.get(d, d)) for d in mode.departments]
    prompt = _build_prompt(mode_id, mode.label, dept_list, caps)

    # v6-U 强制刷新 hub_settings 到 instance — 防 startup hook 没生效 / hub 被改但没 reload
    try:
        from ..hub_settings_store import apply_stored_hub_on_startup
        apply_stored_hub_on_startup()
    except Exception as e:
        _log.warning("apply_stored_hub_on_startup failed: %s", e)

    ceo_model = _ceo_model_now()
    ceo_fallback = _ceo_fallback_now()
    provider = (llm_rag_settings.llm_provider or "").strip().lower()
    base_url = (llm_rag_settings.litellm_base_url or "")
    _log.info(
        "[generate_full_team] mode=%s provider=%s base_url=%s model=%s fallback=%s",
        mode_id, provider, base_url[:60], ceo_model, ceo_fallback,
    )

    if provider != "litellm":
        _log.warning("[generate_full_team] llm_provider=%s != litellm → 走 stub (假团队). 请检查 hub_settings.json 的 llm_provider 字段", provider)
        return _stub_team(mode_id, dept_list)

    # v6-U2 智能 fallback: 同家族同档次模型 (4.7 → 4.6)
    smart_fb = _smart_fallback_for(ceo_model)
    _log.info("[generate_full_team] primary=%s smart_fallback=%s", ceo_model, smart_fb)
    try:
        resp = await litellm_client.complete(
            model=ceo_model,
            fallbacks=smart_fb or None,
            prompt=prompt,
            system=(
                "You are a strict JSON-emitting team architect for the H-SEMAS swarm system. "
                "Output ONLY valid JSON matching the schema. No prose, no markdown fences."
            ),
        )
    except Exception as e:
        _log.exception("[generate_full_team] LLM call 抛异常: %s", e)
        raise
    _log.info("[generate_full_team] LLM 返回 %d 字符", len(resp.text or ""))
    parsed = _try_parse_json(resp.text)
    if not parsed:
        _log.error("[generate_full_team] JSON 解析失败. raw_first_500=%s", (resp.text or "")[:500])
        raise ValueError(f"LLM did not return valid JSON. raw_first_500={resp.text[:500]}")

    parsed = _assign_persona_ids(parsed, mode_id)
    # v6-U 把 LLM 输出里的 native vendor 前缀改写成走用户网关 (防 anthropic/... 直走 native 报 502)
    _patch_team_to_user_gateway(parsed)
    parsed.update({
        "generated_at": int(time.time()),
        "generator_model": resp.raw.get("model", CEO_DEFAULT_MODEL),
    })
    parsed["missing_api_keys"] = _missing_keys_warning(parsed)
    return parsed


async def regenerate_department(mode_id: str, dept_id: str) -> dict[str, Any]:
    """只重生一个部门 (head + staff). 成本 ~¥0.5."""
    from . import team_store
    team = team_store.load_team(mode_id)
    if not team:
        raise KeyError(f"team for {mode_id} not found; call generate first")
    target_dept = next((d for d in team.get("departments") or [] if str(d.get("dept_id")) == dept_id), None)
    if not target_dept:
        raise KeyError(f"dept_id {dept_id} not found in team {mode_id}")

    mode = get_mode(mode_id)
    label = mode.department_labels.get(dept_id, dept_id)
    other_depts = [
        f"  - {d.get('dept_id')} ({d.get('label')}) — head: {(d.get('head') or {}).get('name', '?')}"
        for d in team.get("departments") or [] if str(d.get("dept_id")) != dept_id
    ]
    prompt = f"""为 H-SEMAS {mode_id} ({mode.label}) 场景的【单个部门】重新设计 head + 3 staff。

要重生的部门: {dept_id} ({label})

同场景已有的其它部门 (供避免重复 sub_specialty):
{chr(10).join(other_depts) if other_depts else '(无)'}

可选旗舰模型快照:
```yaml
{yaml.safe_dump(_load_capabilities(), allow_unicode=True, sort_keys=False)}
```

输出 strict JSON, schema (只输出这个部门的对象):
{{
  "dept_id": "{dept_id}",
  "label": "<>",
  "head": {{"persona_id": ..., "name": ..., "title": ..., "sub_specialty": ..., "ocean": {{...}}, "personality": ..., "diagnostic_style": ..., "model_modeA": ..., "model_modeB": ..., "model_vendor": ..., "prompt": ...}},
  "staff": [...]
}}

只输出 JSON。
"""
    resp = await litellm_client.complete(
        model=_ceo_model_now(),
        fallbacks=_smart_fallback_for(_ceo_model_now()) or None,
        prompt=prompt,
        system="Output ONLY valid JSON matching the schema. No prose.",
    )
    parsed = _try_parse_json(resp.text)
    if not parsed:
        raise ValueError(f"LLM did not return valid JSON. raw_first_500={resp.text[:500]}")
    parsed["dept_id"] = dept_id
    fake_team = {"ceo": team.get("ceo") or {}, "departments": [parsed]}
    return _assign_persona_ids(fake_team, mode_id)["departments"][0]


async def regenerate_persona(mode_id: str, dept_id: str, persona_id: str) -> dict[str, Any]:
    """只重生 dept 内一个人设. 成本 ~¥0.2."""
    from . import team_store
    team = team_store.load_team(mode_id)
    if not team:
        raise KeyError(f"team for {mode_id} not found")
    dept = next((d for d in team.get("departments") or [] if str(d.get("dept_id")) == dept_id), None)
    if not dept:
        raise KeyError(f"dept_id {dept_id} not found")

    is_head = (dept.get("head") or {}).get("persona_id") == persona_id
    if is_head:
        old = dept.get("head") or {}
        role_label = "部门主管 (head)"
    else:
        old = next((s for s in dept.get("staff") or [] if s.get("persona_id") == persona_id), None)
        if not old:
            raise KeyError(f"persona_id {persona_id} not found in dept {dept_id}")
        role_label = "职员 (staff)"

    other_personas = [
        f"  - {p.get('name', '?')} ({p.get('sub_specialty', '?')}): {p.get('personality', '')[:50]}"
        for p in ([dept.get("head") or {}] + (dept.get("staff") or []))
        if p.get("persona_id") != persona_id
    ]
    model_hint = "某家旗舰 api_id (见快照)" if is_head else "ollama_chat/qwen2.5:7b-instruct"
    vendor_line = '"model_vendor": "<>",' if is_head else ''
    prompt = f"""为 {dept_id} 部门重新设计一个 {role_label}, 替换原来的:
  原: {old.get('name', '?')} - {old.get('sub_specialty', '?')} - {old.get('personality', '')}

同部门其它人 (供避免重复风格/专科):
{chr(10).join(other_personas) if other_personas else '(无)'}

可选模型 (head 用旗舰, staff 用本地):
```yaml
{yaml.safe_dump(_load_capabilities(), allow_unicode=True, sort_keys=False)}
```

输出 strict JSON 描述这一个人:
{{
  "persona_id": "{persona_id}",
  "name": "<>",
  "title": "<>",
  "sub_specialty": "<>",
  "ocean": {{...}},
  "personality": "<>",
  "diagnostic_style": "<>",
  "model_modeA": "<{model_hint}>",
  "model_modeB": "<>",
  {vendor_line}
  "prompt": "<200-400 字>"
}}

只输出 JSON。
"""
    resp = await litellm_client.complete(
        model=_ceo_model_now(),
        fallbacks=_smart_fallback_for(_ceo_model_now()) or None,
        prompt=prompt,
        system="Output ONLY valid JSON matching the schema. No prose.",
    )
    parsed = _try_parse_json(resp.text)
    if not parsed:
        raise ValueError(f"LLM did not return valid JSON. raw_first_500={resp.text[:500]}")
    parsed["persona_id"] = persona_id
    return parsed


def _stub_team(mode_id: str, dept_list: list[tuple[str, str]]) -> dict[str, Any]:
    """LLM provider 非 litellm 时返回的骨架, 让 UI 能跑通."""
    return {
        "mode_id": mode_id,
        "generated_at": int(time.time()),
        "generator_model": "stub",
        "missing_api_keys": [],
        "ceo": {
            "persona_id": f"ceo_{mode_id}_stub",
            "name": "AI 总顾问 (stub)",
            "title": "会诊主席",
            "model_modeA": CEO_DEFAULT_MODEL,
            "model_modeB": CEO_DEFAULT_MODEL,
            "prompt": "(尚未调用 LLM 生成, 设置里把 LLM provider 调到 litellm 然后重新点 '生成团队')",
        },
        "departments": [
            {
                "dept_id": d,
                "label": label,
                "head": {
                    "persona_id": f"head_{d}_stub",
                    "name": "占位主管", "title": "(stub)",
                    "sub_specialty": "(stub)",
                    "ocean": {"O": 0.5, "C": 0.5, "E": 0.5, "A": 0.5, "N": 0.5},
                    "personality": "(stub)", "diagnostic_style": "(stub)",
                    "model_modeA": "anthropic/claude-sonnet-4-6",
                    "model_modeB": CEO_DEFAULT_MODEL,
                    "model_vendor": "Anthropic", "prompt": "(尚未生成)",
                },
                "staff": [
                    {
                        "persona_id": f"staff_{d}_{i}_stub",
                        "name": f"占位职员{i+1}", "title": "(stub)",
                        "sub_specialty": "(stub)",
                        "ocean": {"O": 0.5, "C": 0.5, "E": 0.5, "A": 0.5, "N": 0.5},
                        "personality": "(stub)", "diagnostic_style": "(stub)",
                        "model_modeA": "ollama_chat/qwen2.5:7b-instruct",
                        "model_modeB": "anthropic/claude-haiku-4-5",
                        "prompt": "(尚未生成)",
                    } for i in range(3)
                ],
            } for d, label in dept_list
        ],
    }
