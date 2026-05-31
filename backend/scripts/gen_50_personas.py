# -*- coding: utf-8 -*-
"""
gen_50_personas.py — 把 scenarios/extra/ 里的"部门骨架"场景, 确定性地补全成
scenarios/teams/{mode_id}.yaml 的完整人设 (CEO + 各部门 head + 3 staff,
含 OCEAN / prompt / 三档模型), 对照黄金模板 family_doctor.yaml。

设计要点 (见 docs/persona-gen-handoff.md):
- 不调 LLM, 纯确定性规则拼装 (0 成本 / 0 网络 / 可重复 / 质量可控)。
- 部门 dept_id / label 原样沿用 extra yaml, 不改。
- CEO 三档: A/B 全 Opus(B 不降级), C 本地。
- head: modeA 旗舰按部门轮换 vendor, modeB 三家便宜云轮换, modeC 本地。
- staff: modeA 本地, modeB 随所属部门 head 的 modeB, modeC 本地 (同黄金模板)。
- 名字 / OCEAN / 经验年限 / 口头禅由 hash(persona_id) 确定, 可复现。
- 跳过 generic_consulting / ops_review; 已存在的 teams/{mode_id}.yaml 不覆盖。

用法:
    cd backend
    python scripts/gen_50_personas.py
"""
import os
import sys
import io
import glob
import hashlib
import yaml

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
except Exception:
    pass

# ---------------------------------------------------------------------------
# 路径
# ---------------------------------------------------------------------------
HERE = os.path.dirname(os.path.abspath(__file__))
EXTRA_DIR = os.path.normpath(os.path.join(HERE, "..", "scenarios", "extra"))
TEAMS_DIR = os.path.normpath(os.path.join(HERE, "..", "scenarios", "teams"))

SKIP = {"generic_consulting", "ops_review"}

GENERATED_AT = 1780000000           # 固定整数, 避免每次 diff (不用 time.time())
GENERATOR_MODEL = "hand-crafted-persona-v1"

# 三档模型常量
OPUS = "openai/claude-opus-4-7"
LOCAL = "ollama/deepseek-r1:8b"
# head modeA 旗舰轮换 (model, vendor) —— 对齐黄金模板的多家旗舰风格
HEAD_A_POOL = [
    ("openai/claude-opus-4-7", "Anthropic"),
    ("openai/deepseek-v4-pro", "DeepSeek"),
    ("openai/gemini-3.1-pro-preview", "Google"),
    ("openai/kimi-k2.5", "Moonshot"),
]
# head/staff modeB 便宜云轮换
HEAD_B_POOL = [
    "openai/deepseek-v4-flash",
    "openai/doubao-seed-2-0-lite-260428",
    "openai/gpt-5.4-mini",
]

# ---------------------------------------------------------------------------
# 中文姓名池 (确定性取用)
# ---------------------------------------------------------------------------
SURNAMES = list(
    "李王张刘陈杨黄赵周吴徐孙马朱胡郭何高林罗郑梁谢宋唐许韩冯邓曹彭曾肖"
    "田董袁潘于蒋蔡余杜叶程苏魏吕丁任沈姚卢钟汪戴姜范方石"
)
GIVEN_CHARS = list(
    "一帆志强培文明越敏锐睿哲思远嘉怡子轩浩然语桐俊杰晓建国立伟雅静婷宇航"
    "鹏飞海涛文博晨曦若清扬正阳天佑承博慧君安宁知行守诚致衡稳实拓"
)


def _hash_int(s):
    return int(hashlib.md5(s.encode("utf-8")).hexdigest(), 16)


def _jit(base, seed, span=0.06):
    """围绕 base 的确定性小幅抖动, 钳制到 [0.05, 0.98], 保留两位小数。"""
    h = _hash_int(seed)
    delta = ((h % 1000) / 1000.0 - 0.5) * 2 * span
    return round(max(0.05, min(0.98, base + delta)), 2)


def _years(seed, lo=15, hi=28):
    return lo + (_hash_int(seed) % (hi - lo + 1))


def _pick(pool, seed):
    return pool[_hash_int(seed) % len(pool)]


def make_name(seed, used):
    """确定性生成不重名的中文姓名 (姓 + 1~2 字名)。"""
    for bump in range(0, 300):
        h = _hash_int(seed + "#" + str(bump))
        surname = SURNAMES[h % len(SURNAMES)]
        g1 = GIVEN_CHARS[(h // 7) % len(GIVEN_CHARS)]
        if (h // 13) % 3 == 0:
            given = g1
        else:
            given = g1 + GIVEN_CHARS[(h // 131) % len(GIVEN_CHARS)]
        name = surname + given
        if name not in used:
            used.add(name)
            return name
    name = "顾问" + str(len(used) + 1)
    used.add(name)
    return name


# ---------------------------------------------------------------------------
# YAML: 让 prompt 用块标量 (|) 输出
# ---------------------------------------------------------------------------
class LiteralStr(str):
    pass


def _literal_representer(dumper, data):
    return dumper.represent_scalar("tag:yaml.org,2002:str", str(data), style="|")


yaml.add_representer(LiteralStr, _literal_representer, Dumper=yaml.SafeDumper)


# ---------------------------------------------------------------------------
# 文案拼装
# ---------------------------------------------------------------------------
def parse_label(label):
    """'空间设计师 (户型动线/采光/功能分区)' -> ('空间设计师', ['户型动线','采光','功能分区'])"""
    s = label.replace("（", "(").replace("）", ")").replace("／", "/")
    short = s.split("(")[0].strip()
    kws = []
    if "(" in s and ")" in s:
        inner = s[s.index("(") + 1: s.rindex(")")]
        kws = [k.strip() for k in inner.split("/") if k.strip()]
    if not kws:
        kws = [short]
    return short, kws


AUDIT_KW = ("审核", "验收", "风控", "合规", "质量", "检查", "风险", "监理", "稽核",
            "法务", "安全", "防伪", "鉴定", "防坑", "守门", "证据", "反对", "毒舌", "评论")
CREATIVE_KW = ("设计", "创意", "风格", "文案", "策划", "视觉", "美容", "造型", "彩妆",
               "内容", "剧本", "叙事", "构图", "调味", "景观", "软装", "导演", "修辞")
ANALYST_KW = ("预算", "财务", "成本", "数据", "分析", "估值", "测算", "运营", "增长",
              "投放", "流量", "统计", "核算", "议价", "谈判", "价")


def role_flavor(short, kw_text):
    text = short + " " + kw_text
    if any(k in text for k in AUDIT_KW):
        return ("audit", dict(O=0.7, C=0.9, E=0.45, A=0.4, N=0.4),
                "严谨挑剔, 凡事先想风险和最坏情况",
                ["把关到底, 不留隐患。", "宁可多查一遍, 不放过一个坑。", "细节里藏着风险。"])
    if any(k in text for k in CREATIVE_KW):
        return ("creative", dict(O=0.85, C=0.7, E=0.65, A=0.6, N=0.3),
                "富有创意, 注重体验和整体感受",
                ["好的体验是设计出来的。", "细节决定质感。", "先打动人, 再谈功能。"])
    if any(k in text for k in ANALYST_KW):
        return ("analyst", dict(O=0.6, C=0.9, E=0.5, A=0.55, N=0.3),
                "数据驱动, 精打细算, 用事实说话",
                ["数字不会骗人。", "先算清账, 再做决定。", "把钱花在刀刃上。"])
    return ("expert", dict(O=0.65, C=0.85, E=0.55, A=0.62, N=0.3),
            "专业稳健, 注重实效和可落地",
            ["专业的事交给专业的人。", "稳扎稳打, 对结果负责。", "把事情一次做对。"])


def head_prompt(name, title, years, short, kws, style):
    steps = ["%d. %s" % (i + 1, k) for i, k in enumerate(kws[:4])]
    steps.append("%d. 给出优先级与可执行建议" % (len(kws[:4]) + 1))
    return LiteralStr(
        "你是%s, %s。%d 年%s相关经验。\n"
        "专科职责: %s。\n"
        "框架: %s。\n"
        "风格: %s。\n"
        "禁忌: 不替用户做最终决定; 不给无依据的保证; 不超出专业范围。\n"
        "输出: 专科判断 → 优先级排序 → 建议行动 → 风险提示。"
        % (name, title, years, short, " / ".join(kws), " ".join(steps), style)
    )


def ceo_prompt(name, title, domain, n_dept):
    return LiteralStr(
        "你是%s, %s。多年%s统筹经验。\n"
        "你的角色: 统筹 %d 位专科顾问的判断, 给用户最终的\"该怎么做 / 先做什么 / 避哪些坑\"。\n"
        "工作流:\n"
        "1. 先扫所有专科意见, 找红线 (风险/合规/安全/预算), 有则第一句提示。\n"
        "2. 按重要性和紧急度排序, 给 top 3 方向 + 各自理由。\n"
        "3. 给\"下一步具体做什么\"的清单 (谁 / 做什么 / 注意点)。\n"
        "4. 强调\"最终决定权在你, 建议多方核实比价\"。\n"
        "禁忌: 不替用户做最终决定; 不给无依据的承诺。\n"
        "输出格式: 必读结论 → top 3 建议 → 行动清单 → 风险提示。"
        % (name, title, domain, n_dept)
    )


def ocean(d):
    return {"O": d["O"], "C": d["C"], "E": d["E"], "A": d["A"], "N": d["N"]}


# ---------------------------------------------------------------------------
# 单个场景 -> team dict (字段对齐 family_doctor.yaml)
# ---------------------------------------------------------------------------
def build_team(skel):
    mode_id = skel["mode_id"]
    label = skel.get("label", mode_id)
    dept_ids = skel["departments"]
    dept_labels = skel.get("department_labels", {})
    n = len(dept_ids)
    used_names = set()

    # ---- CEO ----
    cseed = "ceo_" + mode_id
    ceo_name = make_name(cseed, used_names)
    ceo_title = "%s总顾问" % label
    ceo = {
        "persona_id": "ceo_%s" % mode_id,
        "name": ceo_name,
        "title": ceo_title,
        "sub_specialty": "%s全流程统筹 / 多专科协调" % label,
        "ocean": ocean(dict(
            O=_jit(0.70, cseed + "O"), C=_jit(0.95, cseed + "C", 0.04),
            E=_jit(0.65, cseed + "E"), A=_jit(0.72, cseed + "A"),
            N=_jit(0.22, cseed + "N"))),
        "personality": "资深%s统筹者, 沉稳可靠, 最厌恶踩坑和半途返工。" % label,
        "diagnostic_style": "先卡红线 (风险/预算/合规), 再综合各专科意见排优先级。",
        "model_modeA": OPUS,
        "model_modeB": OPUS,            # CEO B 档不降级
        "model_modeC": LOCAL,
        "model_vendor": "Anthropic",
        "prompt": ceo_prompt(ceo_name, ceo_title, label, n),
    }

    # ---- departments ----
    departments = []
    for i, dept_id in enumerate(dept_ids):
        d_label = dept_labels.get(dept_id, dept_id)
        short, kws = parse_label(d_label)
        _, oc, style, cp_pool = role_flavor(short, "/".join(kws))
        hseed = "head_%s_%s" % (mode_id, dept_id)
        head_name = make_name(hseed, used_names)
        yrs = _years(hseed)
        head_a, vendor = HEAD_A_POOL[i % len(HEAD_A_POOL)]
        head_b = HEAD_B_POOL[i % len(HEAD_B_POOL)]
        head_title = "%s主管" % short

        head = {
            "persona_id": "head_%s_%s" % (mode_id, dept_id),
            "name": head_name,
            "title": head_title,
            "sub_specialty": " / ".join(kws),
            "ocean": ocean(dict(
                O=_jit(oc["O"], hseed + "O"), C=_jit(oc["C"], hseed + "C"),
                E=_jit(oc["E"], hseed + "E"), A=_jit(oc["A"], hseed + "A"),
                N=_jit(oc["N"], hseed + "N"))),
            "personality": "%d 年%s经验, %s。" % (yrs, short, style),
            "diagnostic_style": "围绕 %s 逐项排查, 先抓主要矛盾。" % "、".join(kws[:3]),
            "model_modeA": head_a,
            "model_modeB": head_b,
            "model_modeC": LOCAL,
            "model_vendor": vendor,
            "prompt": head_prompt(head_name, head_title, yrs, short, kws, style),
            "catchphrase": _pick(cp_pool, hseed),
        }

        staff = [
            {
                "persona_id": "staff_%s_%s_assistant" % (mode_id, dept_id),
                "name": "助理-%s" % short,
                "title": "%s资深助理 (10 年)" % short,
                "sub_specialty": "检索查资料 / 案头准备",
                "ocean": ocean(dict(
                    O=_jit(0.50, hseed + "aO"), C=_jit(0.85, hseed + "aC"),
                    E=_jit(0.45, hseed + "aE"), A=_jit(0.80, hseed + "aA"),
                    N=_jit(0.30, hseed + "aN"))),
                "model_modeA": LOCAL,
                "model_modeB": head_b,
                "model_modeC": LOCAL,
                "prompt": LiteralStr(
                    "你是%s的资深助理 (10 年经验, 不是新人)。\n"
                    "职责: 快速检索资料/数据/案例 → 给主管做案头准备。\n"
                    "先列\"主管决策需要的 3-5 项关键信息\"再检索总结。\n"
                    "风格: 高效准确, 不做主观判断。" % head_name),
            },
            {
                "persona_id": "staff_%s_%s_resident" % (mode_id, dept_id),
                "name": "骨干-%s" % short,
                "title": "%s骨干 / 复核" % short,
                "sub_specialty": "落地执行 / 二次复核",
                "ocean": ocean(dict(
                    O=_jit(0.50, hseed + "rO"), C=_jit(0.80, hseed + "rC"),
                    E=_jit(0.50, hseed + "rE"), A=_jit(0.60, hseed + "rA"),
                    N=_jit(0.30, hseed + "rN"))),
                "model_modeA": LOCAL,
                "model_modeB": head_b,
                "model_modeC": LOCAL,
                "prompt": LiteralStr(
                    "你是%s的骨干 / 复核。\n"
                    "职责: 把主管的方向落成可执行细节 + 自查一遍逻辑。\n"
                    "风格: 扎实细致, 注重落地。" % head_name),
            },
            {
                "persona_id": "staff_%s_%s_auditor" % (mode_id, dept_id),
                "name": "审核-%s" % short,
                "title": "%s审核员" % short,
                "sub_specialty": "非常规视角 / 安全合规审查",
                "ocean": ocean(dict(
                    O=_jit(0.70, hseed + "uO"), C=_jit(0.75, hseed + "uC"),
                    E=_jit(0.40, hseed + "uE"), A=_jit(0.35, hseed + "uA"),
                    N=_jit(0.45, hseed + "uN"))),
                "model_modeA": LOCAL,
                "model_modeB": head_b,
                "model_modeC": LOCAL,
                "prompt": LiteralStr(
                    "你是%s审核员。\n"
                    "职责: 用非常规视角找漏洞 + 安全/合规/最坏情况审查。\n"
                    "专挑别人没想到的风险点。\n"
                    "风格: 挑剔严格, 不留情面。" % short),
            },
        ]

        departments.append({
            "dept_id": dept_id,
            "label": d_label,
            "head": head,
            "staff": staff,
        })

    total = 1 + n * 4
    return {
        "mode_id": mode_id,
        "generated_at": GENERATED_AT,
        "generator_model": GENERATOR_MODEL,
        "ceo": ceo,
        "departments": departments,
        "missing_api_keys": [],
        "degradation": {
            "modeA": "高档 — 各专科主管用旗舰模型, 适合复杂疑难。",
            "modeB": "中档 — CEO 用 Opus, 各专科主管轮流用便宜云模型, 日常够用。",
            "modeC": "离线档 — 全本地 ollama/deepseek-r1:8b, 零成本但慢。",
            "local_concurrency_warning": "本地档需在 decision_engine 限 max_concurrent_local_calls=2, 否则 ollama 会过载。",
        },
        "team_size": total,
    }


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def main():
    os.makedirs(TEAMS_DIR, exist_ok=True)
    files = sorted(glob.glob(os.path.join(EXTRA_DIR, "*.yaml")))
    all_pids = {}
    written, skipped = [], []

    for path in files:
        with open(path, "r", encoding="utf-8") as f:
            skel = yaml.safe_load(f)
        if not isinstance(skel, dict) or "mode_id" not in skel:
            skipped.append((os.path.basename(path), "无 mode_id"))
            continue
        mode_id = skel["mode_id"]
        if mode_id in SKIP:
            skipped.append((mode_id, "在跳过名单"))
            continue
        out_path = os.path.join(TEAMS_DIR, mode_id + ".yaml")
        if os.path.exists(out_path):
            skipped.append((mode_id, "teams 已存在, 不覆盖"))
            continue
        if not skel.get("departments"):
            skipped.append((mode_id, "无 departments"))
            continue

        team = build_team(skel)

        # 自检: dept_id 集合一致 + persona_id 全局唯一
        assert [d["dept_id"] for d in team["departments"]] == list(skel["departments"]), \
            "dept_id 不一致: " + mode_id
        ids = [team["ceo"]["persona_id"]]
        for d in team["departments"]:
            ids.append(d["head"]["persona_id"])
            ids.extend(s["persona_id"] for s in d["staff"])
        for pid in ids:
            if pid in all_pids:
                raise AssertionError("persona_id 跨场景重复: " + pid)
            all_pids[pid] = mode_id

        with open(out_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(team, f, allow_unicode=True, sort_keys=False,
                           default_flow_style=False, width=4096)
        written.append((mode_id, team["team_size"]))

    print("=== 生成完成 ===")
    print("写入 %d 个 team.yaml:" % len(written))
    for mid, sz in written:
        print("  %-22s %2d 人 (%d 部门)" % (mid, sz, (sz - 1) // 4))
    print("跳过 %d 个:" % len(skipped))
    for mid, why in skipped:
        print("  %-22s %s" % (mid, why))
    print("全局 persona 总数: %d" % len(all_pids))


if __name__ == "__main__":
    main()
