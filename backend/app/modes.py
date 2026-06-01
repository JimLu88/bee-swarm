from __future__ import annotations

from typing import Any, Literal

from .models import ModeInfo

ModeRegistrySource = Literal["builtin", "extra", "fallback"]
from .scenario_loader import load_scenario_dict

_EXTRA_MODES_CACHE: dict[str, ModeInfo] | None = None


def _builtin_mode_ids() -> frozenset[str]:
    return frozenset(MODES.keys())


def _extra_modes() -> dict[str, ModeInfo]:
    global _EXTRA_MODES_CACHE
    if _EXTRA_MODES_CACHE is None:
        from .extra_mode_loader import load_extra_modes

        _EXTRA_MODES_CACHE = load_extra_modes(builtin_mode_ids=_builtin_mode_ids())
    return _EXTRA_MODES_CACHE


def reload_mode_yaml_cache() -> None:
    """Clear cached extra-mode registry; next ``get_mode`` / ``list_modes`` re-reads ``scenarios/extra/*.yaml``."""
    global _EXTRA_MODES_CACHE
    _EXTRA_MODES_CACHE = None


# v9 横切/动态注入部门的中文名 — 这些部门(视野拓展部 + 通用横切)由 dispatcher/run_decision
# 动态加进 departments, 不在任何 mode 的 department_labels 里, 之前在前端 chip 显示成英文 id。
# /api/modes/lookup 会把本表合并进返回的 department_labels, 一处定义、所有场景生效。
# 横切部门: 跨场景的通用/技术角色.
# - 通用(每个场景都注入, 见 VISION_EXPANSION_DEPTS): out_of_box_breakthrough / parallel_architecture_scout
# - 技术专用(仅程序管理等技术场景, 不进美食/旅行等日常场景): benchmark / xlab / security / arch
CROSSCUTTING_DEPT_LABELS: dict[str, str] = {
    "parallel_architecture_scout": "外部·小众视角",  # 找外网/国外/小众渠道的优质结果(非技术架构)
    "out_of_box_breakthrough": "破局思考",
    "benchmark": "对标基准",
    "xlab": "破局思考部 (X-Lab)",
    "security": "安全合规",
    "arch": "架构设计",
}
# 仅这两个是"每个场景都会注入"的通用横切部门 (与 team_generator.VISION_EXPANSION_DEPTS 对齐).
UNIVERSAL_CROSSCUT_DEPTS = ("parallel_architecture_scout", "out_of_box_breakthrough")


MODES: dict[str, ModeInfo] = {
    "program_management": ModeInfo(
        mode_id="program_management",
        label="程序管理设计",
        # v6-V 改"工序型"(arch/logic/ui/db) → "角色型" (对标 Microsoft/Google 项目评审会):
        # 6 个真实工程师角色, 每个有独立判断力, 不是工序步骤. 横切由 dispatcher 注入.
        departments=["principal_architect", "senior_engineer", "frontend_engineer",
                     "dba", "security_engineer", "qa_engineer"],
        department_labels={
            "principal_architect": "首席架构师 (系统设计/扩展性/技术选型/取舍权衡)",
            "senior_engineer":     "资深工程师 (实现路径/复杂度/可维护性/工时估算)",
            "frontend_engineer":   "前端工程师 (UX/性能/可访问性/状态管理)",
            "dba":                 "DBA / 数据架构师 (schema/索引/查询优化/数据完整性)",
            "security_engineer":   "安全工程师 (注入/权限/密钥/隐私/合规)",
            "qa_engineer":         "QA / 测试架构师 (边界 case/测试矩阵/性能压测/回归)",
        },
    ),
    "family_doctor": ModeInfo(
        mode_id="family_doctor",
        label="家庭医生助手",
        # v6-V MDT 多学科会诊 (按医学专科分, 对标 WHO/Mayo Clinic 家庭医生标准):
        # 内/外/骨/急诊/中医/影像/精神 + 妇产/儿科 = 9 专科. 横切由 dispatcher 自动注入.
        departments=["internal_med", "surgery", "orthopedics", "emergency",
                     "tcm", "radiology", "psych_med", "obgyn", "pediatrics"],
        department_labels={
            "internal_med": "内科 (心血管/呼吸/消化/内分泌/感染)",
            "surgery": "外科 (普外/泌尿/血管/急腹症)",
            "orthopedics": "骨科 (创伤/脊柱/关节/肌肉损伤)",
            "emergency": "急诊医学 (危急识别/红旗征/心梗中风排除)",
            "tcm": "中医 (经络/体质/慢病调理/辨证)",
            "radiology": "影像/检验科 (推荐查什么+怎么读片)",
            "psych_med": "精神/心身医学 (躯体化/焦虑/抑郁/睡眠)",
            "obgyn": "妇产科 (月经/孕产/更年期/妇科肿瘤筛查)",
            "pediatrics": "儿科 (发育/疫苗/常见儿童病/喂养)",
        },
    ),
    "stock_trading": ModeInfo(
        mode_id="stock_trading",
        label="股票交易助手",
        # v6-V 改"分析方法型" → "分析师角色型" (对标真实券商研究部):
        # 6 个不同分析师, 每个有独立判断 + 风格. 横切由 dispatcher 注入.
        departments=["fundamental_analyst", "technical_analyst", "macro_strategist",
                     "industry_researcher", "quant_strategist", "risk_manager"],
        department_labels={
            "fundamental_analyst": "基本面分析师 (财报/估值/业务模型/护城河)",
            "technical_analyst":   "技术分析师 (K线/量价/形态/趋势/支撑阻力)",
            "macro_strategist":    "宏观策略师 (利率/通胀/政策/板块轮动/经济周期)",
            "industry_researcher": "行业研究员 (产业链/竞争格局/上下游/景气度)",
            "quant_strategist":    "量化策略师 (因子/回测/统计套利/异常监控)",
            "risk_manager":        "风控经理 (黑天鹅/仓位/止损/相关性/极端情形)",
        },
    ),
    "travel_planning": ModeInfo(
        mode_id="travel_planning",
        label="旅行计划管理",
        # v6-V 改"任务型"(签证/航班/安全/禁忌) → "角色型" (对标米其林指南 + Lonely Planet 编辑团队):
        # 6 个真实旅行专家角色, 每人都有完整旅行经验和品味. 横切由 dispatcher 注入.
        departments=["itinerary_planner", "local_guide", "foodie_scout",
                     "budget_manager", "safety_advisor", "experience_curator"],
        department_labels={
            "itinerary_planner":   "行程规划师 (天数节奏/动静搭配/交通衔接/签证/航班)",
            "local_guide":         "当地向导 (小众景点/避坑路线/最佳时段/打车攻略)",
            "foodie_scout":        "美食侦察员 (本地老店/必吃菜单/避雷网红店/价位)",
            "budget_manager":      "预算管理员 (省钱组合/性价比/季节差价/隐藏成本)",
            "safety_advisor":      "安全顾问 (治安/医疗/天气/政治风险/紧急联系)",
            "experience_curator":  "体验策展人 (文化禁忌/拍照机位/纪念品挑选/在地仪式)",
        },
    ),
    # v6-A 新增 8 个日常场景, 每个用真实领域专科作 dept_id (全英文 snake_case)
    "legal_consulting": ModeInfo(
        mode_id="legal_consulting",
        label="法律咨询",
        # v6-V 清理: 删旧 benchmark/xlab (dispatcher 自动注入 parallel_arch_scout/out_of_box). 6 法律专科:
        departments=["contract_law", "labor_law", "marriage_inherit", "ip_law", "company_law", "litigation"],
        department_labels={
            "contract_law":     "合同法律师 (买卖/服务/合作; 风险条款 + 漏洞 + 履约争议)",
            "labor_law":        "劳动法律师 (劳动合同/工伤/裁员/竞业/社保争议)",
            "marriage_inherit": "婚姻继承律师 (离婚/财产分割/抚养/遗产/老人赡养)",
            "ip_law":           "知识产权律师 (商标/版权/专利/商业秘密/侵权诉讼)",
            "company_law":      "公司法律师 (股权/章程/治理/兼并收购/股东纠纷)",
            "litigation":       "诉讼律师 (证据/管辖/程序/胜诉率评估/调解 vs 诉讼)",
        },
    ),
    "startup_advisory": ModeInfo(
        mode_id="startup_advisory",
        label="创业咨询",
        # v6-V 清理: 删旧 benchmark/xlab. 6 创业核心角色 (对标 YC / a16z / 真格基金 投后服务):
        departments=["business_strategist", "growth_marketer", "cfo_fundraiser",
                     "legal_compliance_officer", "cto_architect", "people_ops"],
        department_labels={
            "business_strategist":      "商业战略 (商业模式/客户洞察/PMF/护城河/定价)",
            "growth_marketer":          "增长负责人 (获客/转化/留存/裂变/数据驱动)",
            "cfo_fundraiser":           "CFO / 融资官 (财务模型/估值/股权结构/BP/对接资本)",
            "legal_compliance_officer": "法务合规官 (合伙协议/期权池/数据合规/资质审批)",
            "cto_architect":            "CTO / 技术架构 (技术选型/MVP 边界/扩展性/团队招聘)",
            "people_ops":               "组织合伙人 (招聘/股权激励/文化/核心团队搭建)",
        },
    ),
    "learning_planning": ModeInfo(
        mode_id="learning_planning",
        label="学习规划",
        # v6-V 改"目标型" → "角色型" (对标 顶级升学机构 + 学习教练):
        departments=["grad_exam_planner", "overseas_consultant", "cert_coach",
                     "k12_advisor", "language_coach", "learning_strategist"],
        department_labels={
            "grad_exam_planner":   "考研规划师 (择校/复习节奏/科目权重/真题打法/复试)",
            "overseas_consultant": "留学顾问 (院校匹配/文书/标化/推荐信/签证/奖学金)",
            "cert_coach":          "职业证书教练 (CPA/CFA/PMP/法考; 备考时长 + 真题策略)",
            "k12_advisor":         "中小学升学规划 (小升初/中考/高考; 学籍/择校/竞赛/选科)",
            "language_coach":      "语言考试教练 (雅思/托福/GRE/小语种; 听说读写各题型)",
            "learning_strategist": "学习策略师 (元认知/费曼法/间隔重复/拖延/精力管理)",
        },
    ),
    "child_education": ModeInfo(
        mode_id="child_education",
        label="儿童教育",
        # v6-V 改"年龄阶段混杂" → "角色型" (对标顶级教育研究所 + 儿童心理诊所):
        departments=["early_childhood_specialist", "academic_tutor", "child_psychologist",
                     "talent_coach", "family_therapist", "pediatric_nutritionist"],
        department_labels={
            "early_childhood_specialist": "幼教专家 (0-6 岁认知/语言/运动/社交发展评估)",
            "academic_tutor":             "学科辅导师 (语数英/学法/写作业/考试焦虑/补差培优)",
            "child_psychologist":         "儿童心理咨询师 (情绪/注意力/对抗/校园关系/学习障碍)",
            "talent_coach":               "特长教练 (音体美/编程/科创; 兴趣判别 + 长期培养路径)",
            "family_therapist":           "家庭关系治疗师 (夫妻教育分歧/二胎/隔代育儿/离异家庭)",
            "pediatric_nutritionist":     "儿童营养师 (挑食/身高/过敏/疫苗/睡眠/视力)",
        },
    ),
    "dining_recommendation": ModeInfo(
        mode_id="dining_recommendation",
        label="餐饮推荐",
        # v6-V 改"场景型" → "角色型" (对标米其林评审 + 大众点评 KOL 编辑团队):
        departments=["local_foodie", "michelin_critic", "host_concierge",
                     "diet_consultant", "value_hunter", "festive_specialist"],
        department_labels={
            "local_foodie":      "本地老饕 (街边老店/隐藏菜单/本地人才知道的小馆子)",
            "michelin_critic":   "米其林评论员 (菜品创意/摆盘/服务/酒水搭配/星级标准)",
            "host_concierge":    "商务宴请总管 (位次/酒水/隐私性/谈事氛围/账单礼仪)",
            "diet_consultant":   "饮食顾问 (低卡/低嘌呤/孕妇/儿童/过敏/宗教忌口)",
            "value_hunter":      "性价比党 (人均/分量/团购券/隐藏优惠/避坑指南)",
            "festive_specialist":"节日民俗专家 (中秋/年夜饭/寿宴/答谢宴; 习俗 + 寓意)",
        },
    ),
    "nutrition_fitness": ModeInfo(
        mode_id="nutrition_fitness",
        label="营养健身",
        # v6-V 改"分析维度型" → "角色型" (对标顶级私教工作室 + 三甲运动医学科):
        departments=["personal_trainer", "dietitian", "sports_medicine_doc",
                     "rehab_therapist", "mindset_coach", "gear_reviewer"],
        department_labels={
            "personal_trainer":    "私人教练 (动作处方/分化训练/周期化/进阶曲线)",
            "dietitian":           "注册营养师 (宏量配比/赤字盈余/食谱实操/补剂判断)",
            "sports_medicine_doc": "运动医学医生 (受伤评估/慢病相容/激素/心率区间)",
            "rehab_therapist":     "康复理疗师 (代偿动作/筋膜放松/活动度/疼痛排查)",
            "mindset_coach":       "运动心理教练 (坚持机制/反弹防控/动机/习惯设计)",
            "gear_reviewer":       "装备评测员 (鞋/服/器械/可穿戴, 测评 + 性价比)",
        },
    ),
    "purchase_decision": ModeInfo(
        mode_id="purchase_decision",
        label="采购决策",
        # v6-V 改"研究维度型" → "角色型" (对标 Wirecutter + 消费者报告 + 二手党):
        departments=["product_engineer", "long_term_user", "second_hand_trader",
                     "financial_planner", "sales_insider", "alternative_advocate"],
        department_labels={
            "product_engineer":   "产品工程师 (硬件参数/做工/工艺缺陷/真假鉴别)",
            "long_term_user":     "深度用户 (用了 1 年才知道的优缺点/翻车场景/真实续航)",
            "second_hand_trader": "二手党 (保值率/转手难度/折旧曲线/什么时候出手)",
            "financial_planner":  "财务规划师 (分期 vs 全款/机会成本/月供占比/是否该买)",
            "sales_insider":      "销售线人 (经销商套路/谈判砍价/赠品标配/最佳购买窗口)",
            "alternative_advocate":"替代派 (不买这个能怎么办/租赁/共享/旧物改造)",
        },
    ),
    "tax_insurance": ModeInfo(
        mode_id="tax_insurance",
        label="税务保险",
        # v6-V 微调: 改"主题型" → "角色型" (对标顶级家族办公室 + 持牌财务顾问):
        departments=["personal_tax_advisor", "wealth_planner", "insurance_broker",
                     "pension_advisor", "estate_lawyer", "tax_compliance_auditor"],
        department_labels={
            "personal_tax_advisor":  "个人税务师 (个税/经营所得/股权激励/海外所得)",
            "wealth_planner":        "财富规划师 (资产配置/家庭现金流/教育/购房/养老)",
            "insurance_broker":      "持牌保险经纪 (重疾/医疗/年金/财产; 跨公司横向对比)",
            "pension_advisor":       "养老规划顾问 (社保/企业年金/个税递延/退休缺口测算)",
            "estate_lawyer":         "遗产传承律师 (遗嘱/信托/赠与/跨境遗产/家族治理)",
            "tax_compliance_auditor":"税务合规审计 (税务稽查应对/避税与节税边界/CRS)",
        },
    ),
    # v6-V 新增: 通用咨询 (之前后端没定义, fallback 到 program_management 是错的)
    "generic_consulting": ModeInfo(
        mode_id="generic_consulting",
        label="通用咨询",
        # 对标麦肯锡/波士顿/贝恩三大咨询的标准 case team 组合 + 跨域智库:
        # 用户问任何"不限定领域"的问题, 这 6 个不同视角的通用专家都能给出独特判断
        departments=["strategic_advisor", "domain_researcher", "data_analyst",
                     "user_psychologist", "devils_advocate", "futurist"],
        department_labels={
            "strategic_advisor": "战略顾问 (拆解问题/MECE/框架化思考/排优先级/给行动方案)",
            "domain_researcher": "领域研究员 (扫学术 + 行业报告 + 案例库, 给事实+数据)",
            "data_analyst":      "数据分析师 (能量化的全量化/统计推断/可视化/避免观察偏差)",
            "user_psychologist": "用户心理学家 (从行为/动机/认知偏差/情绪 角度看问题)",
            "devils_advocate":   "魔鬼代言人 (专门找漏洞: 假设 / 数据 / 推理 / 执行可行性)",
            "futurist":          "未来学家 (5-10 年外推/技术 S 曲线/黑天鹅/范式转移)",
        },
    ),
}


def _apply_scenario_yaml(base: ModeInfo) -> ModeInfo:
    raw = load_scenario_dict(base.mode_id)
    if not raw:
        return base
    updates: dict[str, Any] = {"scenario_yaml": f"{base.mode_id}.yaml"}
    if raw.get("label"):
        updates["label"] = str(raw["label"]).strip()
    if raw.get("scenario_description") is not None:
        updates["scenario_description"] = str(raw.get("scenario_description") or "").strip() or None
    if raw.get("default_task_hint") is not None:
        updates["default_task_hint"] = str(raw.get("default_task_hint") or "").strip() or None
    dl = raw.get("department_labels")
    if isinstance(dl, dict):
        merged = dict(base.department_labels)
        for k, v in dl.items():
            ks, vs = str(k), str(v)
            if ks in base.departments:
                merged[ks] = vs
        updates["department_labels"] = merged
    gs = raw.get("gene_seeds")
    if isinstance(gs, dict) and gs:
        merged_seeds = dict(base.gene_seeds or {})
        for k, v in gs.items():
            ks = str(k)
            if ks in base.departments and v is not None:
                merged_seeds[ks] = str(v).strip()
        updates["gene_seeds"] = merged_seeds
    return base.model_copy(update=updates)


def resolve_mode(mode_id: str) -> tuple[ModeInfo, ModeRegistrySource]:
    """
    Resolve ``mode_id`` to a ``ModeInfo`` (with root ``scenarios/{id}.yaml`` overlay applied).

    Unknown ids fall back to built-in ``program_management`` (``registry=fallback``), matching ``get_mode`` semantics.
    """
    if mode_id in MODES:
        return _apply_scenario_yaml(MODES[mode_id]), "builtin"
    extra = _extra_modes().get(mode_id)
    if extra is not None:
        return _apply_scenario_yaml(extra), "extra"
    return _apply_scenario_yaml(MODES["program_management"]), "fallback"


def get_mode(mode_id: str) -> ModeInfo:
    return resolve_mode(mode_id)[0]


def list_modes() -> list[ModeInfo]:
    core = [_apply_scenario_yaml(m) for m in MODES.values()]
    extras = [_apply_scenario_yaml(m) for _, m in sorted(_extra_modes().items(), key=lambda kv: kv[0])]
    return core + extras


def list_extra_mode_ids() -> list[str]:
    """``mode_id`` values registered from ``backend/scenarios/extra/*.yaml`` (not in built-in ``MODES``)."""
    return sorted(_extra_modes().keys())

