# v7 UI 重构 + 富媒体 + 30 预设场景 — 实施计划

> 状态: 已与用户确认所有决策, 待执行. 用户选择「一次性全做」.
> 原则: KISS / 不破坏现有决策链路 / 浅色主题用 CSS 令牌一处切换.

---

## 0. 决策汇总 (用户已拍板)

| # | 议题 | 决定 |
|---|------|------|
| 1 | 复杂度 vs 路线×轮数 重叠 | **方案 C**(单一"努力程度"4档滑块) + 「⚙ 更多设置」按钮展开 **方案 A**(5路线×3轮数 复杂设置) |
| 2 | 主题 黑底→白底 | **全局翻浅色 + 深/浅切换**(CSS 变量令牌层, ☀/🌙 开关) |
| 3 | 成本/预算显示 | **全删** — 前台完全不显示成本(删 BudgetRing + 删复杂度成本标签 + 不显示预估) |
| 4 | 自定义场景生成 | 向导=模板+AI补全; **另预生成 50 个场景, 手写完整 yaml, 放到全部其他工作之后最后做, 写前提示用户** |
| 5 | 顾问团(部门+人设)位置 | 跟场景设置一起, 进**设置抽屉的第一个 tab**(不单开路由) |
| 6 | /trends 趋势页 | **删掉**, 爬虫能力复用到富媒体聚合 |
| 7 | 富媒体范围 | 普通显示单回答 + 「富文本/📎展开更多」按钮显示爬虫聚合(图/文/视频/其他) + markdown 富文本渲染 + 答案下方信息流 + 爬虫图文聚合进答案 |
| 8 | "黑体"含义 | **黑色的字**(浅色主题黑字白底) |
| 9 | 执行范围 | 一次性全做; 50 场景留到最后 |
| 10 | 富媒体技术栈 | **9 个整合**(用户勾选): react-markdown / shadcn/ui / Recharts / ECharts / Tremor / 图墙Masonry / lightbox / Framer Motion / React Flow. (Mermaid 未勾, 列为可选后补) |

---

## 1. 布局重构 (Wave 1)

### 目标结构 (用户视图首页)
```
┌─────────────────────────────────────┐
│ [场景下拉 ▼  家庭医生助手]   ☀/🌙  ⚙设置 │  ← 顶部: 场景下拉 + 主题开关 + 设置入口
├─────────────────────────────────────┤
│  ┌───────────────────────────────┐  │
│  │  输入框 (最上, 最显眼)          │  │  ← 输入框置顶
│  │  📎附件条                       │  │
│  └───────────────────────────────┘  │
│  努力程度: 🟢简单 🟡一般 🔴深入 ⚫全力   │  ← 方案C 单滑块
│  [⚙ 更多设置 ▾]  → 展开 5路线×3轮数    │  ← 方案A 折叠在此
│  [🎯 让CEO先分析]  [🚀 直接开跑]        │
├─────────────────────────────────────┤
│  CEO 预分析 / 路线选择区 (preflight后)  │
├─────────────────────────────────────┤
│  结果 ResultPanel (👍👎 + 富媒体)       │
│  历史 HistoryPanel                     │
└─────────────────────────────────────┘
```

### 场景设置 → SettingsDrawer 的【第一个 tab】(不单开路由)
- 新 tab "🎬 场景" 放在 SettingsDrawer 最前面, 默认第一个
- 内容: ModePicker 完整版(场景分组选择) + TeamPanel(部门+人设, 重生/编辑) + 自定义场景向导入口 + 50 预设场景库浏览
- 顶部场景下拉点"管理/换场景"→ 打开 SettingsDrawer 并定位到该 tab(复用已有 initialTab 机制)

### 改动文件
- `BeeSwarmShell.tsx`: 重排 user 视图顺序; 顶部加场景下拉(轻量) + 主题开关; 移除 BudgetRing 调用; 把 ModePicker/TeamPanel 从首页移到 SettingsDrawer
- `SettingsDrawer.tsx`: 新增 "scenario" tab 放最前; initialTab 支持 "scenario"
- 新建 `ScenarioDropdown.tsx`(顶部轻量下拉, 区别于完整 ModePicker)

---

## 2. 复杂度合并 方案C + 更多设置 (Wave 1)

### 方案C: 单一"努力程度"滑块
- 4 档: 简单 / 一般 / 深入 / 全力 (复用现有 DifficultySlider 视觉, **去掉成本标签**)
- 每档映射 `(route, rounds)`:
  | 努力度 | route | rounds | 说明 |
  |--------|-------|--------|------|
  | 简单 | ceo_only / single | 1 | CEO直答或单部门 |
  | 一般 | multi(CEO选) | 1-2 | 多部门并行 |
  | 深入 | key/multi | 2-3 | 重点部门多轮 |
  | 全力 | all | 3-5 | 全部门深度辩论 |
- 滑块旁「⚙ 更多设置 ▾」→ 展开现有 `RoutePlanner`(5路线×3轮数, CEO预填+SOP推荐), 允许覆盖滑块的默认映射
- bandit 记录仍用最终生效的 (route, rounds_band, difficulty)

### 改动文件
- `DifficultySlider.tsx`: 删 cost 字段显示; 语义改"努力程度"
- `RoutePlanner.tsx`: 改成可折叠"高级"模式; 接受滑块传入的默认值
- `BeeSwarmShell.tsx`: 滑块↔路线联动; effort→(route,rounds) 映射表

---

## 3. 成本/预算 全删 (Wave 1)
- 删 `BudgetRing` 组件调用(BeeSwarmShell L447-448)
- 删 DifficultySlider 的 `约X元` 标签
- 删 `/estimate` 返回的 estimate_yuan 在前台的展示(后端端点保留, 前台不渲染)
- ResultPanel 的 `total_cost_yuan` 成本小条移除前台显示
- 注: 后端成本记账(ledger)保留, 只是主界面不显示; 想看去 ⚙设置

---

## 4. 主题: 全局浅色 + 深/浅切换 (Wave 2 — 最大工程)

### 策略: CSS 变量令牌层 (一处定义, 全站生效)
建 `app/globals.css` (或 theme.css) 定义令牌:
```css
:root[data-theme="light"] {
  --bg: #ffffff; --bg-elev: #f5f6f8; --bg-card: #fafbfc;
  --text: #1a1a1a; --text-dim: #555; --text-faint: #888;
  --border: rgba(0,0,0,0.12); --accent: #2563eb; --accent-bg: rgba(37,99,235,0.10);
  --good: #16a34a; --warn: #d97706; --bad: #dc2626;
}
:root[data-theme="dark"] {  /* 保留旧深色 */
  --bg: #0f0f12; --text: #ffffff; --border: rgba(255,255,255,0.10); ...
}
```
- 顶部 ☀/🌙 开关 → 切 `document.documentElement.dataset.theme` + localStorage 持久化(注意 SSR hydration: 初值固定, useEffect 读 localStorage, 跟 tier 同样的坑)
- **批量替换**: 把各组件内联的 `rgba(255,255,255,...)` / `#0f0f12` / `color:"#fff"` 等硬编码深色 → `var(--xxx)`
- 字体: 浅色下黑字; 中文无衬线栈兜底 `font-family: system-ui, "PingFang SC", "Microsoft YaHei", sans-serif`(用户只要黑色字, 字体族用系统默认)

### 范围(约 40+ 文件含内联深色)
- 重灾区(用户点名): NotificationCenter(通知中心 v3-K)、SwarmDashboardModal(AI干活弹窗)
- 全部 v2/ 组件 + viz/ 子组件 + modal 类
- 先建令牌 + 改全局壳 → 再逐组件替换 → 最后扫剩余硬编码色

---

## 5. 自定义场景向导 + 30 预设场景 (Wave 3)

### 5a. 预生成 50 个场景 (手写完整 yaml, **最后做**)
- **顺序**: 放到 Wave 1-4 全部完成之后才做; 动手写之前先提示用户确认清单
- **方式**: 手写完整 yaml(用户选 a, 0 LLM 费用), 与现有 13 个同格式:
  ceo + departments[head+staff×3] + model_mode A/B/C + OCEAN + diagnostic_style + prompt
- 落地 `backend/scenarios/teams/<mode_id>.yaml` + `backend/app/modes.py` 注册 mode_id/label/departments/department_labels
- 50 场景候选清单见 §7(待用户增删)
- 工作量提示: 50 × ~800 行 ≈ 4万行, 分批写, 每批写完 AST 校验

### 5b. 自定义场景向导 (内联, 取代"去进阶加YAML")
分步问答 wizard:
1. **你想咨询什么领域?** → 给一堆预设选项(法律/医疗/装修/育儿/投资/留学/...) + 自定义输入框
2. **典型问题举例?** → 让用户写 1-2 个例子(帮 AI 理解)
3. **希望从哪些角度分析?** → AI 根据前两步草拟 4-6 个部门, 用户勾选/增删
4. **模型档位偏好?** → 高/中/本地
5. 预览生成的团队(CEO+部门+人设草稿) → 确认/微调 → 落地成新场景
- 「AI 帮我完善」按钮: 调便宜模型把草稿补全成完整人设(OCEAN+prompt)
- 后端复用 `team_generator.py` + `team_store.save_team`; mode 注册走 `scenarios/extra/*.yaml`(已有动态加载机制)

### 改动文件
- 新建 `ScenarioWizard.tsx`(替换 ScenarioYamlAuthor 入口)
- 后端 `team_api.py` 加 wizard 端点(草拟/确认/落地)
- `modes.py` / extra modes 加载已支持

---

## 6. 富媒体呈现 (Wave 4)

### 6a. 默认: 单回答 markdown 富文本渲染
- 引入 **react-markdown + remark-gfm + rehype**(安全, 无 XSS, 组件化自定义渲染)
- 渲染: 表格 / 图片URL / 代码块 / mermaid 流程图 / 列表
- 自定义 renderer 把特定块渲染成卡片(callout/警告/方案对比表)

### 6b. 答案下方「📎 富文本 / 展开更多」按钮 → 信息流
- 点开展开: 各部门原文卡片 + 爬虫抓到的链接/图片/视频 聚合成 **信息流(feed)/Bento 网格**
- 爬虫: 复用现有 bee-scraper(HN/arxiv/github/tavily/brave) — 决策时顺带抓相关图文
- 卡片类型: 文字摘要卡 / 图片卡 / 视频嵌入卡(爬到的链接) / 来源链接卡

### 6c. 爬虫图文聚合进答案
- 决策流里让相关部门(或新"资讯聚合"角色)调 scraper 抓图文 → 结构化存入 summary → 前端信息流渲染

### 技术栈 (用户已多选确认 — 10 个全整合)
| 用途 | 库 | 角色 |
|------|-----|------|
| 答案富文本渲染 | **react-markdown** + remark-gfm | 地基(必备) ✓ |
| 卡片/手风琴原语 | **shadcn/ui** | 信息流卡片/折叠骨架 ✓ |
| AI 文字→图 (可选后补) | Mermaid | 流程图/时序图 — 用户未勾, 暂不做 |
| 日常图表 | **Recharts** | 柱/折/饼 轻量 |
| 重数据图表 | **Apache ECharts** | 10w点/3D/地图/金融 |
| Bento 区块 | **Tremor** | 信息块布局 |
| 图墙瀑布流 | **react-grid-gallery / Masonry** | 爬虫图片自适应 |
| 图片/视频查看 | **yet-another-react-lightbox** | 灯箱大图+视频 |
| 展开动效 | **Framer Motion** | 📎展开更多 丝滑 |
| 决策流程图 | **React Flow (xyflow)** | 部门协作/决策DAG |

- 依赖体积控制: ECharts/ReactFlow/Three 类按需 dynamic import, 不进首屏 bundle
- 安全: react-markdown 默认禁 raw HTML; 爬虫来的 URL 做白名单/转义

### 改动文件
- 新建 `RichAnswer.tsx`(markdown 渲染 + 展开更多)
- 新建 `InfoFeed.tsx` / `BentoGrid.tsx`(信息流/卡片)
- ResultPanel 接入; 删 `/trends` 路由 + TrendsDashboard, 爬虫逻辑迁过来
- 后端: decision summary 增加 `media_cards` 字段(爬虫图文)

---

## 7. 50 预设场景候选清单 (待你过目/增删)

> 现有 13: family_doctor / program_management / stock_trading / travel_planning / legal_consulting / startup_advisory / learning_planning / child_education / dining_recommendation / nutrition_fitness / purchase_decision / tax_insurance / generic_consulting

新增 50 候选(生活/职场学习/专业创业/健康心理/兴趣文化 五大类):
**生活类(1-12)**: 1.装修设计 2.租房买房 3.汽车选购维保 4.婚礼策划 5.宠物养护 6.家庭理财 7.保险规划 8.老人赡养照护 9.家政/收纳整理 10.园艺绿植 11.数码3C选购 12.二手交易/闲置
**职场/学习(13-24)**: 13.简历求职面试 14.职业规划转行 15.英语/语言学习 16.考研考公 17.留学申请 18.PPT/演讲汇报 19.写作润色 20.时间管理效率 21.谈薪/晋升 22.副业/自由职业 23.职场人际/沟通 24.技能考证
**专业/创业(25-38)**: 25.电商运营 26.短视频/自媒体起号 27.私域/社群运营 28.SEO/网站增长 29.产品经理需求分析 30.UI/UX设计评审 31.合同/法务审查 32.专利/知识产权 33.数据分析/BI 34.AI提示词工程 35.跨境电商/外贸 36.农业/种植养殖 37.投融资/BP 38.品牌/公关营销
**健康/心理(39-46)**: 39.健康体检解读 40.心理情绪疏导 41.两性/亲密关系 42.减肥塑形 43.慢病管理 44.睡眠改善 45.中医养生 46.孕产育儿(0-3岁)
**兴趣/文化(47-50)**: 47.摄影/修图 48.游戏攻略/电竞 49.音乐/乐器学习 50.读书/影评荐书

(每个含 CEO + 5-7 真专科部门 + 各 3 staff 人设, 三档模型, OCEAN, prompt)

---

## 8. 执行批次 (用户选"一次性全做", 50 场景最后, 按依赖排序)

**Wave 1 — 布局骨架 + 复杂度 + 删成本** (低风险, 先见效)
1. 删 BudgetRing + 成本标签 + ResultPanel 成本小条
2. 布局重排(输入框置顶 + 顶部场景下拉 + 主题开关占位)
3. 复杂度方案C 努力程度滑块 + ⚙更多设置展开 RoutePlanner
4. 场景设置/顾问团 移进 SettingsDrawer 第一个 tab

**Wave 2 — 主题令牌层 + 全局浅色 + 切换** (最大工程)
5. globals.css 令牌 + 主题 Context + ☀/🌙 开关(SSR-safe)
6. 逐组件深色→令牌(重灾区优先: 通知中心/AI干活弹窗)

**Wave 3 — 富媒体 10 件套 + 删 /trends**
7. 装依赖 + react-markdown 渲染(RichAnswer)
8. Mermaid + Recharts/ECharts(dynamic import)
9. 「📎展开更多」信息流: Tremor Bento + 图墙Masonry + lightbox + Framer Motion 动效
10. React Flow 决策DAG
11. 爬虫图文聚合进 summary.media_cards; 删 /trends + 迁爬虫

**Wave 4 — 自定义场景向导**
12. ScenarioWizard(分步问答 + AI补全) + 后端 wizard 端点

**Wave 5 — 50 预设场景 (最后做, 写前提示用户)**
13. 手写 50 份完整 team.yaml + modes 注册, 分批 AST 校验

每 wave 末: py_compile + tsc 验证.

---

## 9. 已确认 (无遗留待定)
- 30 场景生成方式 → **(a) 手写完整 yaml**, 数量 **50**, 放**最后**做, 写前提示
- 场景页 → **SettingsDrawer 第一个 tab**(不单开路由)
- 富媒体 → **10 个全整合**(见 §6 表)
- 主题 → 全局浅色 + 深浅切换
