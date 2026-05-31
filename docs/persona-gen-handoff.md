# 50 场景人设补全 — 交接文档 (persona-gen-handoff)

> 目的: 给「新窗口对话」一份自包含说明, 让它把 50 个**只有部门骨架、没有人设**的场景,
> 补全成 13 个老场景那样的**完整 team.yaml** (CEO + 各部门 head + 3 staff, 含 OCEAN/prompt/三档模型)。
>
> 用户决策: **不调 LLM, 用确定性脚本按部门中文职责拼装** (0 成本/0 网络/可重复/质量可控)。

---

## 1. 当前真实状态 (2026-05-31 核实)

| 类型 | 路径 | 状态 |
|---|---|---|
| 13 老场景 | `backend/scenarios/teams/*.yaml` | ✅ 完整人设 (黄金模板) |
| 50 新场景 | `backend/scenarios/extra/*.yaml` | ⚠️ **只有部门骨架, 零人设** |

- `scenarios/extra/` 实际有 **51 个** yaml: 50 个新场景 + `generic_consulting.yaml` + `ops_review.yaml` (后两个是旧的, 别动)。
- 50 新场景每个: `mode_id / label / scenario_description / departments[6] / department_labels{}`。
- 13 老场景已注册在 `backend/app/modes.py` 的 `MODES` 字典里, **不要碰**。
- 50 新场景通过 `scenarios/extra/*.yaml` 动态加载 (见 `app/extra_mode_loader.py` + `app/modes.py::_extra_modes()`)。
- 运行时 `list_modes()` 返回 **63 个** (13 builtin + 50 extra)。

### 决策引擎怎么用人设 (关键)
`backend/app/decision_engine.py::_run_dept` (约 L102-124):
- `load_team(mode_id)` 读 `scenarios/teams/{mode_id}.yaml`。
- **有** team.yaml → 用 head 的 `prompt` 当 system prompt + 按 tier 取 `model_mode{A/B/C}`。
- **没有** team.yaml → fallback 到 `build_initial_gene_prompt` (通用 "你是 X 部门 Lead"), 人设很弱。
→ 所以 50 场景现在能跑但人设平庸; 补全 team.yaml 后才有真专科人格。

---

## 2. 完整 team.yaml schema (照 `family_doctor.yaml` 抄)

### 顶层
```yaml
mode_id: home_renovation
generated_at: 1780060800          # 固定整数即可 (别用 time.time(), 否则每次 diff)
generator_model: hand-crafted-v7  # 标记手写
ceo: {...}
departments: [{...}]
missing_api_keys: []
degradation:
  modeA: "高档 — 各家旗舰, ~¥0.5-1.5/决策, 30-90s"
  modeB: "中档 — CEO Opus 不变 + head 用 deepseek-v4-flash/doubao-seed/gpt-5.4-mini 轮流, ~¥0.05-0.2/决策, 20-50s"
  modeC: "离线档 — 全本地 ollama/deepseek-r1:8b, ¥0 但慢 (单次约 10-20 分钟)"
  local_concurrency_warning: "本地档需在 decision_engine 限 max_concurrent_local_calls=2, 否则 ollama 会过载"
```

### CEO (字段全)
```yaml
ceo:
  persona_id: ceo_<modeabbr>_<拼音名>      # 如 ceo_hr_fangyue
  name: 方越                                # 中文姓名(虚构)
  title: 装修总顾问
  sub_specialty: 装修全流程统筹 / 多工种协调
  ocean: {O: 0.7, C: 0.95, E: 0.65, A: 0.7, N: 0.25}   # CEO 普遍高 C 低 N
  personality: 15 年装修行业经验, 沉稳。最讨厌: 增项陷阱 + 货不对板。
  diagnostic_style: 先卡预算红线再谈效果; 综合各工种意见排优先级。
  model_modeA: openai/claude-opus-4-7       # CEO A/B 都 Opus (B 档 CEO 不降级!)
  model_modeB: openai/claude-opus-4-7
  model_modeC: ollama/deepseek-r1:8b
  model_vendor: Anthropic
  prompt: |
    你是方越, 装修总顾问。15 年行业经验。
    你的角色: 综合 6 位专科顾问的判断, 给用户最终的"该怎么装/预算怎么分/避哪些坑"。
    工作流:
    1. 扫各专科意见, 找红线 (预算爆/安全隐患/合同坑), 有则第一句提示。
    2. 按重要性排序建议: top 3 + 各自理由。
    3. 给"下一步具体做什么"清单。
    4. 强调"最终决定权在你, 建议多方比价"。
    禁忌: 不推荐具体品牌/商家; 不替用户签约。
    输出格式: 必读结论 → top 3 建议 → 行动清单 → 风险提示。
```

### 部门 head (字段同 CEO)
```yaml
departments:
- dept_id: space_designer            # 必须 == extra yaml 里的 departments[i]
  label: 空间设计师 (户型动线/采光/功能分区)   # == extra 的 department_labels[dept_id]
  head:
    persona_id: head_hr_space_designer_<拼音>
    name: 苏明
    title: 资深空间设计师
    sub_specialty: 住宅空间 / 小户型优化
    ocean: {O: 0.85, C: 0.8, E: 0.6, A: 0.6, N: 0.35}  # 按角色性格调 (设计师高 O, 审核高 C 低 A)
    personality: 一句话人物小传 (经验年限 + 性格特点 + 立场)。
    diagnostic_style: 这个专科的思考框架一句话。
    model_modeA: openai/claude-opus-4-7    # head A 档可旗舰; 也可按部门轮流换 vendor (见 §3)
    model_modeB: openai/deepseek-v4-flash  # head B 档降级 (轮流: deepseek-v4-flash/doubao-seed-2-0-lite-260428/gpt-5.4-mini)
    model_modeC: ollama/deepseek-r1:8b
    model_vendor: Anthropic
    prompt: |
      你是<name>, <title>。<经验>。
      框架: 1.<步骤> 2.<步骤> 3.<步骤> ...
      风格: <口头禅/态度>。
      (~150-220 字)
  staff: [ {助理}, {主治/复核}, {审核员} ]   # 固定 3 人, 见下
```

### staff (固定 3 人套路, 字段精简: 无 model_vendor)
> 每个部门固定这 3 个角色, 名字/prompt 随部门职责换:
1. **资深助理 (10 年经验, 检索查资料)** — `title: <部门>资深助理 (10 年)`, ocean 高 A; prompt: "你是 X 主任的资深助理(10年,不是新人)。职责: 快速检索资料/数据/案例→给主任做案头。先列'主任决策需要的 3-5 项关键信息'再检索总结。风格: 高效准确, 不主观判断。"
2. **主治/复核 (中坚执行)** — `title: <部门>主治/复核`, ocean 均衡; prompt: "你是 X 的主治/骨干。职责: 把主任的方向落成可执行细节 + 自查一遍逻辑。"
3. **审核员 (非常规视角 + 安全)** — `title: <部门>审核员`, ocean 高 O 低 A 中 N (爱挑刺); prompt: "你是 X 的审核员。职责: 用非常规视角找漏洞 + 安全/合规/最坏情况审查。专挑别人没想到的。"

staff 三档模型统一: `model_modeA: ollama/deepseek-r1:8b` (注: 老模板 staff 的 A 档就是本地, 省钱), `model_modeB: openai/deepseek-v4-flash`, `model_modeC: ollama/deepseek-r1:8b`。
(若想 staff A 档也用云端, 改成便宜云即可——但老模板是本地, 建议沿用。)

---

## 3. head 模型轮换 (B 档省钱多样性)
老场景 head 的 `model_modeB` 在 3 个便宜云里轮流, 避免全压一个:
`openai/deepseek-v4-flash` / `openai/doubao-seed-2-0-lite-260428` / `openai/gpt-5.4-mini`
按部门 index % 3 分配即可。CEO 的 B 档**永远 Opus 不降级**。

---

## 4. 脚本怎么读 50 场景
脚本直接遍历 `scenarios/extra/*.yaml`, 跳过 `generic_consulting` 和 `ops_review`, 读每个的
`mode_id / label / scenario_description / departments / department_labels`, 按上面 schema 生成
`scenarios/teams/{mode_id}.yaml`。**部门 id 和 label 必须原样沿用 extra 里的, 不要改。**
(50 个 mode_id 以 `ls scenarios/extra/` 实际文件为准, 别硬编码清单。)

---

## 5. 给新窗口的推荐做法 (确定性脚本)

写 `backend/scripts/gen_50_personas.py`:
1. 遍历 `scenarios/extra/*.yaml` (排除 generic_consulting/ops_review)。
2. 对每个场景, 用**确定性规则**(非 LLM)拼:
   - 中文姓名: 从一个姓氏池 + 名字池按 hash(dept_id) 取, 保证不重复、可复现。
   - CEO + 每个 head + 3 staff 的字段, 按 §2 模板填; prompt 用 department_labels 里括号内的职责关键词拼成"框架/风格/禁忌"。
   - OCEAN 按角色类型给基线 (CEO/设计型/审核型/助理型) + 小幅 hash 抖动。
   - model 三档按 §2/§3 规则分配。
3. `yaml.safe_dump(..., allow_unicode=True, sort_keys=False)` 写 `scenarios/teams/{mode_id}.yaml`。
4. 自检: 每个 team 的 dept_id 集合 == extra 的 departments; persona_id 全局唯一。

### 验证
```bash
cd backend
python scripts/gen_50_personas.py
python -c "from app.persona.team_store import load_team; t=load_team('home_renovation'); print(len(t['departments']), 'depts', t['ceo']['name'])"
# 重启 8100, 前端选'装修设计'跑一个任务, 看各部门是否有真专科人设 (不再是'你是X部门Lead')
```

---

## 6. 黄金模板文件 (直接读它对照)
`backend/scenarios/teams/family_doctor.yaml` (801 行, 9 部门 37 人, 最全)
或更小的 `backend/scenarios/teams/child_education.yaml` (6 部门 25 人, 标准规模)。

## 7. 不要碰
- `backend/app/modes.py` 的 MODES (13 builtin)
- `scenarios/teams/*.yaml` 里已有的 13 个
- `scenarios/extra/generic_consulting.yaml`, `ops_review.yaml`
- 前端任何文件 (v7 UI 已完成且 build 通过)
