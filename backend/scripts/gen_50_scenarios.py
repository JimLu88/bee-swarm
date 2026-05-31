# -*- coding: utf-8 -*-
"""v7 W5: 批量生成 50 个自定义场景骨架 → scenarios/extra/*.yaml.
每个场景含真实「专科/角色」部门分工 (5-7 个), 对标该领域世界一流团队.
人设(OCEAN+prompt)首次使用时由 team_generator pipeline 自动生成并永久存档.
用法: python scripts/gen_50_scenarios.py
"""
import sys, io
from pathlib import Path
import yaml

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
EXTRA = Path(__file__).resolve().parent.parent / "scenarios" / "extra"
EXTRA.mkdir(parents=True, exist_ok=True)

SCENARIOS = [
    ("home_renovation", "装修设计", "新房/旧房装修全流程决策", [
        ("space_designer", "空间设计师 (户型动线/采光/功能分区)"),
        ("budget_controller", "预算控制师 (报价拆解/防增项/性价比)"),
        ("material_expert", "材料专家 (主辅材/环保/耐用度/品牌)"),
        ("construction_supervisor", "施工监理 (工艺标准/验收/水电防坑)"),
        ("style_curator", "风格软装师 (色彩/家具/灯光/氛围)"),
        ("contract_advisor", "合同顾问 (装修合同/付款节点/维权)")]),
    ("rent_buy_house", "租房买房", "租房或购房的选择与谈判", [
        ("location_analyst", "地段分析师 (交通/学区/配套/升值)"),
        ("price_negotiator", "议价谈判师 (砍价策略/市场行情/底价)"),
        ("legal_checker", "产权法务 (产权/合同/抵押/纠纷排查)"),
        ("finance_planner", "贷款规划师 (首付/月供/利率/组合贷)"),
        ("inspection_expert", "验房专家 (质量/隐患/朝向/噪音)"),
        ("risk_advisor", "风险顾问 (政策/烂尾/二手坑)")]),
    ("car_purchase", "汽车选购维保", "买车/换车/养车决策", [
        ("vehicle_analyst", "车型分析师 (需求匹配/参数/对标)"),
        ("price_negotiator", "购车谈判师 (裸车价/优惠/赠品/全款分期)"),
        ("reliability_expert", "可靠性专家 (故障率/保值率/口碑)"),
        ("maintenance_advisor", "维保顾问 (保养成本/质保/配件)"),
        ("insurance_planner", "保险规划师 (险种/理赔/费用)"),
        ("trade_in_expert", "置换二手师 (旧车估值/过户/避坑)")]),
    ("wedding_planning", "婚礼策划", "婚礼筹备全流程", [
        ("wedding_planner", "婚礼策划总监 (流程/主题/时间线)"),
        ("budget_manager", "预算管家 (分项控制/防超支/性价比)"),
        ("venue_scout", "场地餐饮顾问 (场地/菜单/档期)"),
        ("vendor_coordinator", "供应商协调 (摄影/化妆/司仪/四大金刚)"),
        ("etiquette_advisor", "习俗礼仪师 (彩礼/流程/双方家庭)"),
        ("guest_experience", "宾客体验师 (邀请/座位/伴手礼)")]),
    ("pet_care", "宠物养护", "猫狗等宠物健康与养育", [
        ("vet_advisor", "宠物医师 (疾病/疫苗/急症识别)"),
        ("nutrition_expert", "宠物营养师 (粮食/喂养/体重)"),
        ("behavior_trainer", "行为训练师 (行为/训练/分离焦虑)"),
        ("grooming_expert", "美容护理师 (毛发/皮肤/清洁)"),
        ("cost_planner", "养宠成本顾问 (医疗/用品/保险)"),
        ("breed_advisor", "品种适配顾问 (选宠/性格/家庭匹配)")]),
    ("health_checkup", "体检报告解读", "体检/化验单看不懂找它", [
        ("general_physician", "全科医师 (综合判读/异常分级)"),
        ("lab_interpreter", "检验解读师 (血常规/生化/肿瘤标志物)"),
        ("imaging_reader", "影像解读师 (B超/CT/结节/钙化)"),
        ("chronic_disease_advisor", "慢病管理师 (三高/血糖/趋势)"),
        ("lifestyle_coach", "生活干预师 (饮食/运动/作息建议)"),
        ("referral_advisor", "就医指引 (要不要进一步查/挂什么科)")]),
    ("mental_wellness", "心理情绪疏导", "压力/焦虑/情绪困扰陪伴", [
        ("clinical_psychologist", "临床心理师 (评估/认知行为/危机识别)"),
        ("emotion_coach", "情绪教练 (即时安抚/正念/调节)"),
        ("relationship_advisor", "关系顾问 (亲密/家庭/职场人际)"),
        ("sleep_specialist", "睡眠专家 (失眠/作息/放松)"),
        ("growth_mentor", "成长导师 (自我认知/价值/意义感)"),
        ("safety_gatekeeper", "安全守门员 (高危识别/转介专业)")]),
    ("family_finance", "家庭理财", "工资/存款/资产配置规划", [
        ("financial_planner", "理财规划师 (目标/资产配置/现金流)"),
        ("investment_advisor", "投资顾问 (基金/股票/风险偏好)"),
        ("insurance_planner", "保险规划师 (保障缺口/险种/性价比)"),
        ("tax_optimizer", "税务优化师 (个税/专项扣除/合规)"),
        ("debt_manager", "负债管理师 (房贷/消费贷/优先级)"),
        ("retirement_planner", "养老规划师 (养老金/长期/复利)")]),
    ("insurance_planning", "保险规划", "买什么保险/避坑/理赔", [
        ("insurance_architect", "保险架构师 (家庭保障体系/优先级)"),
        ("product_analyst", "产品分析师 (条款/对比/性价比)"),
        ("claim_advisor", "理赔顾问 (健康告知/理赔/拒赔避坑)"),
        ("health_underwriter", "核保顾问 (既往症/投保策略)"),
        ("budget_allocator", "预算分配师 (保费占比/期限/搭配)"),
        ("risk_assessor", "风险评估师 (家庭风险敞口/缺口)")]),
    ("elder_care", "老人赡养照护", "父母养老/照护/医疗安排", [
        ("geriatric_advisor", "老年医学顾问 (慢病/用药/认知)"),
        ("care_planner", "照护规划师 (居家/机构/护工方案)"),
        ("finance_coordinator", "养老财务师 (费用/养老金/资产)"),
        ("legal_advisor", "法务顾问 (遗嘱/赡养/财产)"),
        ("psych_support", "心理支持师 (老人情绪/家属压力)"),
        ("emergency_planner", "应急预案师 (突发/就医/联络)")]),
    ("resume_interview", "简历求职面试", "简历优化与面试准备", [
        ("resume_expert", "简历专家 (结构/亮点/ATS 关键词)"),
        ("interview_coach", "面试教练 (行为面/压力面/话术)"),
        ("industry_insider", "行业内行 (岗位真相/薪资/前景)"),
        ("salary_negotiator", "薪资谈判师 (报价/谈薪/offer 对比)"),
        ("personal_brand", "个人品牌师 (定位/作品集/领英)"),
        ("hr_perspective", "HR 视角 (筛选逻辑/红线/背调)")]),
    ("career_transition", "职业规划转行", "跳槽/转行/职业路径", [
        ("career_strategist", "职业战略师 (路径/赛道/长期定位)"),
        ("skill_gap_analyst", "技能差距分析师 (现状/缺口/补齐)"),
        ("industry_researcher", "行业研究员 (趋势/红利/风险)"),
        ("transition_planner", "转型规划师 (步骤/过渡/止损)"),
        ("financial_advisor", "财务顾问 (现金流/空窗期/风险)"),
        ("risk_devil", "反对派 (转行陷阱/最坏情况)")]),
    ("language_learning", "语言学习", "英语/日语等语言学习规划", [
        ("curriculum_designer", "课程设计师 (路径/教材/进度)"),
        ("method_coach", "方法教练 (输入输出/记忆/沉浸)"),
        ("exam_strategist", "考试策略师 (雅思/托福/应试技巧)"),
        ("speaking_partner", "口语陪练 (发音/表达/纠错)"),
        ("motivation_keeper", "动力管理师 (坚持/习惯/反馈)"),
        ("resource_curator", "资源策展师 (App/书/媒体/性价比)")]),
    ("grad_civil_exam", "考研考公", "考研/考公/考编规划", [
        ("exam_strategist", "应试战略师 (院校/岗位/分数线/性价比)"),
        ("subject_planner", "科目规划师 (公共课/专业课/时间表)"),
        ("method_coach", "学习方法教练 (刷题/笔记/记忆)"),
        ("info_researcher", "信息研究员 (招录/政策/报录比)"),
        ("mental_coach", "心态教练 (焦虑/坚持/瓶颈)"),
        ("interview_prep", "面试复试官 (复试/面试/调剂)")]),
    ("study_abroad", "留学申请", "本/硕/博海外申请", [
        ("admission_strategist", "申请战略师 (选校/定位/梯度)"),
        ("essay_advisor", "文书顾问 (PS/CV/推荐信/故事)"),
        ("test_planner", "标化规划师 (语言/GRE/时间线)"),
        ("country_expert", "国别专家 (各国政策/费用/前景)"),
        ("finance_planner", "留学财务师 (预算/奖学金/汇率)"),
        ("visa_advisor", "签证顾问 (材料/面签/拒签风险)")]),
    ("presentation_skills", "PPT演讲汇报", "做 PPT / 上台演讲/工作汇报", [
        ("narrative_architect", "叙事架构师 (逻辑/金字塔/故事线)"),
        ("slide_designer", "视觉设计师 (排版/图表/视觉锤)"),
        ("delivery_coach", "演讲教练 (台风/控场/紧张)"),
        ("audience_analyst", "受众分析师 (听众/痛点/说服)"),
        ("data_storyteller", "数据叙事师 (数字/图表/可信度)"),
        ("qa_simulator", "答辩模拟官 (尖锐提问/应对)")]),
    ("writing_polish", "写作润色", "文章/公文/文案写作与改稿", [
        ("structure_editor", "结构编辑 (谋篇/逻辑/节奏)"),
        ("language_polisher", "语言润色师 (措辞/文采/简洁)"),
        ("style_adapter", "文体适配师 (公文/营销/学术/自媒体)"),
        ("fact_checker", "事实核查员 (准确/引用/严谨)"),
        ("audience_lens", "读者视角 (可读性/共鸣/传播)"),
        ("critic", "毒舌评论员 (找毛病/挑刺)")]),
    ("time_productivity", "时间管理效率", "拖延/效率/精力管理", [
        ("system_designer", "效率系统设计师 (GTD/方法论/工具)"),
        ("priority_coach", "优先级教练 (要事/取舍/四象限)"),
        ("habit_engineer", "习惯工程师 (习惯养成/触发/复利)"),
        ("energy_manager", "精力管理师 (节律/休息/专注)"),
        ("procrastination_buster", "拖延克星 (拆解/启动/反拖延)"),
        ("tool_curator", "工具策展师 (App/自动化/性价比)")]),
    ("ecommerce_ops", "电商运营", "淘宝/拼多多/抖店运营", [
        ("operations_lead", "运营操盘手 (策略/节奏/数据)"),
        ("traffic_expert", "流量专家 (付费/自然/搜索/推荐)"),
        ("conversion_optimizer", "转化优化师 (详情/价格/评价)"),
        ("supply_chain", "供应链顾问 (选品/库存/成本)"),
        ("content_creator", "内容创意师 (主图/详情/直播)"),
        ("data_analyst", "数据分析师 (ROI/复购/漏斗)")]),
    ("short_video", "短视频自媒体", "抖音/小红书/B站起号", [
        ("account_strategist", "账号战略师 (定位/赛道/人设)"),
        ("content_director", "内容导演 (选题/脚本/钩子)"),
        ("traffic_hacker", "流量增长师 (算法/标签/破播放)"),
        ("production_expert", "制作专家 (拍摄/剪辑/封面)"),
        ("monetization_advisor", "变现顾问 (广告/带货/知识付费)"),
        ("data_optimizer", "数据复盘师 (完播/互动/迭代)")]),
    ("private_domain", "私域社群运营", "微信/社群/会员运营", [
        ("private_strategist", "私域战略师 (引流/承接/转化/复购)"),
        ("community_operator", "社群运营师 (活跃/活动/氛围)"),
        ("ip_builder", "人设打造师 (朋友圈/信任/专业感)"),
        ("conversion_designer", "成交设计师 (话术/SOP/路径)"),
        ("retention_expert", "复购留存师 (会员/裂变/LTV)"),
        ("tool_advisor", "工具顾问 (SCRM/自动化/合规)")]),
    ("seo_growth", "SEO网站增长", "网站流量/SEO/增长", [
        ("seo_strategist", "SEO 战略师 (关键词/架构/意图)"),
        ("content_engineer", "内容工程师 (产出/质量/EEAT)"),
        ("tech_seo", "技术 SEO (速度/索引/结构化)"),
        ("link_builder", "外链建设师 (权重/外链/品牌)"),
        ("analytics_expert", "数据分析师 (GA/转化/归因)"),
        ("growth_hacker", "增长黑客 (实验/裂变/渠道)")]),
    ("product_manager", "产品需求分析", "产品经理/需求/PRD", [
        ("product_strategist", "产品战略师 (定位/路线/取舍)"),
        ("user_researcher", "用户研究员 (画像/痛点/场景)"),
        ("requirement_analyst", "需求分析师 (优先级/PRD/边界)"),
        ("ux_advisor", "交互体验顾问 (流程/可用性/原型)"),
        ("data_pm", "数据产品师 (指标/AB/北极星)"),
        ("dev_liaison", "研发对接 (可行性/成本/排期)")]),
    ("ui_ux_review", "UI/UX设计评审", "界面/交互设计评审优化", [
        ("visual_designer", "视觉设计师 (排版/色彩/层次)"),
        ("interaction_designer", "交互设计师 (流程/反馈/状态)"),
        ("usability_expert", "可用性专家 (易用/认知负荷/无障碍)"),
        ("design_system", "设计系统师 (组件/规范/一致性)"),
        ("brand_aligner", "品牌对齐师 (调性/识别/情感)"),
        ("dev_feasibility", "前端可行性 (实现/性能/还原度)")]),
    ("contract_review", "合同法务审查", "合同/协议条款审查", [
        ("contract_lawyer", "合同律师 (条款/权责/漏洞)"),
        ("risk_assessor", "风险评估师 (违约/争议/敞口)"),
        ("clause_specialist", "条款专家 (付款/知产/保密/竞业)"),
        ("dispute_advisor", "争议顾问 (管辖/仲裁/救济)"),
        ("compliance_checker", "合规审查师 (法规/红线/效力)"),
        ("negotiation_advisor", "谈判顾问 (修改/让步/底线)")]),
    ("ip_patent", "专利知识产权", "专利/商标/版权保护", [
        ("patent_attorney", "专利代理师 (检索/撰写/布局)"),
        ("trademark_expert", "商标专家 (注册/分类/驳回)"),
        ("ip_strategist", "知产战略师 (布局/组合/护城河)"),
        ("infringement_analyst", "侵权分析师 (FTO/规避/维权)"),
        ("valuation_advisor", "价值评估师 (转化/许可/作价)"),
        ("compliance_advisor", "合规顾问 (流程/期限/风险)")]),
    ("data_analytics", "数据分析BI", "数据分析/报表/BI", [
        ("analytics_lead", "分析负责人 (问题定义/指标体系)"),
        ("data_engineer", "数据工程师 (清洗/建模/管道)"),
        ("viz_expert", "可视化专家 (图表/仪表盘/叙事)"),
        ("stats_advisor", "统计顾问 (显著性/相关因果/陷阱)"),
        ("business_translator", "业务翻译官 (数据→决策/落地)"),
        ("tool_advisor", "工具顾问 (SQL/BI/Python/性价比)")]),
    ("prompt_engineering", "AI提示词工程", "Prompt/AI 应用调优", [
        ("prompt_architect", "提示架构师 (结构/角色/约束)"),
        ("eval_engineer", "评测工程师 (基准/A/B/回归)"),
        ("rag_advisor", "RAG 顾问 (检索/上下文/幻觉)"),
        ("cost_optimizer", "成本优化师 (token/模型选型/缓存)"),
        ("safety_reviewer", "安全审查师 (越狱/注入/合规)"),
        ("workflow_designer", "工作流设计师 (Agent/链路/工具)")]),
    ("cross_border", "跨境电商外贸", "亚马逊/独立站/外贸", [
        ("market_strategist", "市场战略师 (选品/选市场/定位)"),
        ("platform_operator", "平台运营师 (Listing/广告/排名)"),
        ("logistics_expert", "物流供应链 (头程/海外仓/时效)"),
        ("compliance_advisor", "合规顾问 (关税/认证/VAT/知产)"),
        ("payment_advisor", "收款风控师 (收款/汇率/封号)"),
        ("brand_builder", "品牌出海师 (品牌/独立站/红人)")]),
    ("agriculture", "农业种植养殖", "种植/养殖/农业经营", [
        ("agronomist", "农艺师 (品种/土壤/栽培/病虫)"),
        ("animal_husbandry", "畜牧师 (饲养/防疫/繁育)"),
        ("market_advisor", "市场顾问 (行情/销路/品牌/电商)"),
        ("cost_planner", "成本核算师 (投入/产出/补贴)"),
        ("tech_advisor", "农技顾问 (设备/灌溉/智慧农业)"),
        ("policy_advisor", "政策顾问 (补贴/土地/合作社)")]),
    ("fitness_plan", "健身训练计划", "增肌/减脂/塑形训练", [
        ("training_coach", "训练教练 (计划/动作/周期)"),
        ("nutrition_planner", "营养规划师 (热量/三大营养素/食谱)"),
        ("sports_medicine", "运动医学 (损伤/恢复/疼痛)"),
        ("body_analyst", "体测分析师 (体脂/围度/进度)"),
        ("habit_coach", "习惯教练 (坚持/动力/作息)"),
        ("equipment_advisor", "装备顾问 (器械/补剂/性价比)")]),
    ("skincare_beauty", "护肤美妆", "护肤/美妆/医美决策", [
        ("dermatology_advisor", "皮肤顾问 (肤质/成分/问题肌)"),
        ("ingredient_analyst", "成分分析师 (功效/搭配/刺激)"),
        ("routine_designer", "护肤流程师 (步骤/早晚/换季)"),
        ("medical_beauty", "医美顾问 (项目/风险/恢复)"),
        ("makeup_artist", "彩妆师 (妆容/产品/场合)"),
        ("budget_advisor", "预算顾问 (平替/性价比/避坑)")]),
    ("sleep_health", "睡眠健康", "失眠/睡眠质量改善", [
        ("sleep_physician", "睡眠医师 (失眠/呼吸暂停/病因)"),
        ("cbt_coach", "认知行为师 (CBT-I/睡眠限制/刺激控制)"),
        ("circadian_expert", "节律专家 (生物钟/光照/作息)"),
        ("environment_advisor", "环境顾问 (床品/光声温/设备)"),
        ("stress_reducer", "压力调节师 (放松/焦虑/睡前)"),
        ("lifestyle_coach", "生活干预师 (咖啡因/运动/饮食)")]),
    ("chronic_disease", "慢病管理", "三高/糖尿病等慢病管理", [
        ("chronic_physician", "慢病医师 (诊断/用药/监测)"),
        ("nutrition_therapist", "营养治疗师 (饮食/控糖/控盐)"),
        ("exercise_therapist", "运动治疗师 (适宜运动/强度)"),
        ("medication_advisor", "用药顾问 (依从/副作用/相互作用)"),
        ("monitoring_coach", "监测教练 (指标/记录/趋势)"),
        ("complication_watch", "并发症预警 (红旗征/筛查)")]),
    ("parenting_baby", "婴幼儿养育", "0-3岁喂养/护理/早教", [
        ("pediatric_advisor", "儿科顾问 (发育/疫苗/常见病)"),
        ("feeding_expert", "喂养专家 (母乳/辅食/营养)"),
        ("sleep_trainer", "睡眠引导师 (作息/夜醒/哄睡)"),
        ("early_education", "早教启蒙师 (认知/感统/互动)"),
        ("safety_advisor", "安全顾问 (居家/意外/急救)"),
        ("parent_support", "家长支持师 (产后/分工/情绪)")]),
    ("travel_deep", "深度旅行定制", "小众/深度/自由行定制", [
        ("itinerary_designer", "行程设计师 (路线/节奏/亮点)"),
        ("local_expert", "在地专家 (小众/文化/避坑)"),
        ("budget_planner", "预算规划师 (机酒/性价比/分配)"),
        ("foodie_guide", "美食向导 (餐厅/小吃/预订)"),
        ("safety_advisor", "安全顾问 (治安/医疗/应急)"),
        ("experience_curator", "体验策展师 (独特体验/拍照/纪念)")]),
    ("photography", "摄影技巧", "拍照/构图/后期提升", [
        ("composition_master", "构图大师 (构图/视角/光线)"),
        ("gear_advisor", "器材顾问 (相机/镜头/性价比)"),
        ("lighting_expert", "用光专家 (自然光/布光/氛围)"),
        ("post_processing", "后期修图师 (调色/Lightroom/PS)"),
        ("genre_specialist", "题材专家 (人像/风光/街拍)"),
        ("style_curator", "风格策展师 (审美/参考/个人风格)")]),
    ("cooking_recipe", "烹饪料理", "做菜/菜谱/厨艺提升", [
        ("chef_advisor", "主厨顾问 (菜式/火候/技法)"),
        ("ingredient_expert", "食材专家 (选购/搭配/时令)"),
        ("nutrition_balancer", "营养搭配师 (均衡/健康/热量)"),
        ("flavor_designer", "调味设计师 (味型/酱汁/层次)"),
        ("kitchen_advisor", "厨房顾问 (工具/效率/储存)"),
        ("cuisine_specialist", "菜系专家 (中西日/地方/创新)")]),
    ("gardening", "园艺植物", "养花/种菜/绿植养护", [
        ("horticulturist", "园艺师 (品种/习性/养护)"),
        ("soil_expert", "土肥专家 (土壤/施肥/配土)"),
        ("pest_advisor", "病虫防治师 (病害/虫害/防治)"),
        ("design_advisor", "景观设计师 (搭配/布置/美感)"),
        ("watering_coach", "水肥管理师 (浇水/光照/季节)"),
        ("beginner_guide", "新手向导 (易养/避坑/工具)")]),
    ("music_learning", "乐器学习", "钢琴/吉他等乐器学习", [
        ("instrument_teacher", "乐器导师 (技法/指法/练习)"),
        ("music_theory", "乐理顾问 (基础/视唱/和声)"),
        ("practice_coach", "练习教练 (计划/效率/坚持)"),
        ("repertoire_advisor", "曲目顾问 (选曲/难度/进阶)"),
        ("gear_advisor", "器材顾问 (乐器/选购/性价比)"),
        ("motivation_keeper", "动力管理师 (兴趣/反馈/瓶颈)")]),
    ("fashion_styling", "穿搭造型", "服装搭配/形象提升", [
        ("stylist", "造型师 (搭配/风格/场合)"),
        ("body_analyst", "身型分析师 (体型/扬长避短)"),
        ("color_consultant", "色彩顾问 (肤色/季型/配色)"),
        ("wardrobe_planner", "衣橱规划师 (胶囊衣橱/单品/预算)"),
        ("trend_advisor", "潮流顾问 (流行/经典/个人)"),
        ("budget_shopper", "省钱买手 (性价比/平替/避坑)")]),
    ("board_game", "桌游策略", "桌游/棋牌/策略游戏", [
        ("strategy_master", "策略大师 (战术/布局/博弈)"),
        ("game_selector", "游戏选品师 (推荐/人数/类型)"),
        ("rules_expert", "规则专家 (规则/裁判/争议)"),
        ("beginner_coach", "新手教练 (入门/技巧/进阶)"),
        ("group_host", "组局主持 (氛围/节奏/破冰)"),
        ("collection_advisor", "收藏顾问 (购买/扩展/性价比)")]),
    ("home_organize", "家居收纳整理", "断舍离/收纳/空间整理", [
        ("organize_consultant", "整理顾问 (断舍离/分类/方法)"),
        ("storage_designer", "收纳设计师 (空间/工具/动线)"),
        ("habit_coach", "习惯教练 (维持/复乱/系统)"),
        ("space_optimizer", "空间优化师 (小户型/扩容/利用)"),
        ("product_advisor", "好物顾问 (收纳品/性价比/避坑)"),
        ("mindset_coach", "心态教练 (囤积/纠结/取舍)")]),
    ("gift_selection", "送礼选购", "节日/商务/人情送礼", [
        ("gift_strategist", "送礼策略师 (对象/场合/预算/心意)"),
        ("product_curator", "好物策展师 (品类/品牌/独特)"),
        ("etiquette_advisor", "礼仪顾问 (人情/分寸/禁忌)"),
        ("budget_planner", "预算规划师 (档次/性价比/搭配)"),
        ("personalize_expert", "个性定制师 (定制/惊喜/纪念)"),
        ("backup_advisor", "应急方案师 (临时/快速/万能款)")]),
    ("event_planning", "活动策划", "聚会/团建/生日会策划", [
        ("event_director", "活动总监 (主题/流程/亮点)"),
        ("budget_manager", "预算管家 (分项/控制/性价比)"),
        ("venue_coordinator", "场地协调 (场地/餐饮/设备)"),
        ("entertainment_designer", "节目设计师 (游戏/互动/气氛)"),
        ("logistics_planner", "执行统筹 (物料/时间/分工)"),
        ("guest_experience", "宾客体验师 (邀请/体验/纪念)")]),
    ("debate_speech", "辩论口才", "辩论/即兴表达/沟通力", [
        ("argument_strategist", "论证战略师 (立论/框架/攻防)"),
        ("rhetoric_coach", "修辞教练 (表达/感染力/金句)"),
        ("logic_analyst", "逻辑分析师 (谬误/漏洞/反驳)"),
        ("delivery_coach", "台风教练 (气场/节奏/临场)"),
        ("rebuttal_specialist", "反驳专家 (质询/拆解/反击)"),
        ("audience_reader", "受众洞察师 (评委/听众/说服)")]),
    ("collectibles", "收藏投资", "手办/球鞋/字画等收藏", [
        ("appraisal_expert", "鉴定专家 (真伪/品相/年代)"),
        ("market_analyst", "市场分析师 (行情/趋势/估值)"),
        ("investment_advisor", "投资顾问 (升值/流动性/风险)"),
        ("authenticity_checker", "防伪鉴别师 (假货/翻新/避坑)"),
        ("preservation_expert", "养护专家 (保存/修复/展示)"),
        ("acquisition_advisor", "购藏顾问 (渠道/议价/时机)")]),
    ("digital_office", "数码办公选购", "电脑/手机/办公设备选购", [
        ("device_analyst", "数码分析师 (需求匹配/参数/对标)"),
        ("value_hunter", "性价比猎手 (价格/促销/平替)"),
        ("durability_expert", "耐用评估师 (做工/寿命/售后)"),
        ("ecosystem_advisor", "生态顾问 (系统/配件/互联)"),
        ("scenario_matcher", "场景匹配师 (办公/创作/游戏)"),
        ("anti_trap_advisor", "防坑顾问 (翻新/虚标/陷阱)")]),
    ("dispute_rights", "消费维权", "退款/投诉/消费纠纷维权", [
        ("rights_lawyer", "维权法务 (法条/证据/赔偿)"),
        ("complaint_strategist", "投诉策略师 (渠道/话术/升级)"),
        ("evidence_advisor", "证据顾问 (保全/录音/凭证)"),
        ("negotiation_expert", "协商专家 (谈判/和解/底线)"),
        ("channel_navigator", "渠道领航员 (12315/平台/媒体)"),
        ("cost_assessor", "成本评估师 (时间/精力/胜算)")]),
]


def main():
    written = 0
    for mode_id, label, desc, depts in SCENARIOS:
        data = {
            "mode_id": mode_id,
            "label": label,
            "scenario_description": desc,
            "departments": [d[0] for d in depts],
            "department_labels": {d[0]: d[1] for d in depts},
        }
        (EXTRA / f"{mode_id}.yaml").write_text(
            yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
        written += 1
    ids = [s[0] for s in SCENARIOS]
    dups = sorted({x for x in ids if ids.count(x) > 1})
    assert not dups, f"DUPLICATE mode_id: {dups}"
    print(f"Done. {written} scenario yamls written.")
    print(f"Unique mode_ids: {len(set(ids))}")


if __name__ == "__main__":
    main()
