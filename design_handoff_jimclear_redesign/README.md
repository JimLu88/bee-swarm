# Handoff: H-SEMAS 界面改造 —— Jim Clear 视觉 + Gemini 式聊天

## Overview

把 **H-SEMAS（「我的 AI 智囊团」多智能体决策应用）** 的前端界面，从现有的深色、emoji-heavy、单列堆叠布局，改造成 **Jim Clear 设计系统**（Clarity Blue 主色 + Lexend 字体 + 柔和卡片）的视觉语言，同时把整个交互重排成 **Gemini 最新版的对话式布局**（左侧栏 + 居中对话流 + 底部圆角输入框）。

核心交互链路（CEO 分诊 → 多部门并行讨论 → 红队 → 综合）**完全不变**，只改"长相"和"信息编排"。这与仓库里 `docs/v7-ui-redesign-plan.md` 的方向一致（浅色令牌层、删成本、努力程度滑块、输入框置顶），本次把它推进到"Gemini 对话流 + Jim Clear 皮肤"的完成态。

## ⭐ v3 增量（本次更新）

在原有主聊天界面之外，本版新增 / 修订了以下内容，**请一并落地**：

1. **弥散阴影（diffuse shadow）**：`--shadow-*` 令牌全部改为 Gemini 式大模糊、低透明、冷蓝调、负 spread 的柔和阴影（见「主题令牌」）。**所有卡片统一引用令牌，不要再写一次性 `box-shadow`**——这正是之前「卡片阴影生硬」的根因（一次性 `box-shadow: var(--shadow-sm)` 配旧 token）。
2. **完整深色模式（day / night）**：`colors_and_type.css` 现含 `:root[data-theme="dark"]` 整套语义令牌。切换只需在 `<html>` 上加 / 去 `data-theme="dark"`，**业务代码零改动**。建议在设置页提供「浅色 / 深色 / 跟随系统」三档，并把选择写入 `localStorage('h-semas:theme')`，初值在 `useEffect` 里读取（避免 SSR hydration 报错）。
3. **更大、更清晰的字号**：原界面字偏小。次级 / 元信息文字统一上调约 1–2px（详见「字体」），卡片标题 ≥15.5px、正文 15–17px、统计数字 19–26px。请对照 `screenshots/` 还原层级。
4. **图标系统统一**：全程 Material Symbols **Rounded**，圆形图标按钮一律「大外圈 + 小字形」（见「Gemini 图标按钮规范」）。替换掉真实项目里风格不一的旧图标。
5. **新增两个完整页面**：**设置页**（`showSettings`）与**「我的 / 个人」页**（`showProfile`），组件规范见下方「设置 / 个人页」。

---

## About the Design Files

本包里的 `prototype/index.html` 是一份 **用纯 HTML/CSS/原生 JS 写的设计参考稿**，用来展示**目标外观和交互行为**，**不是**可以直接拷进项目的生产代码。

你的任务是 **在现有 Next.js + React + TypeScript 代码库里，用它已有的模式（function component、内联 style 对象 / CSS 变量、`"use client"`）把这份设计重新实现出来**——也就是改造现有的 `frontend/components/v2/*` 组件，而不是把这个 HTML 塞进去。原型里的 JS（`buildAnswer`、`runDeliberation` 等）只是为了让静态稿动起来，**真实数据流仍走现有的 WebSocket / REST**（`/api/decision/start`、`decision/stream`、`/api/memory` 等，逻辑别动）。

## Fidelity

**高保真（hifi）。** 颜色、字体、间距、圆角、阴影、动效都是最终值，请按本文档的 Design Tokens 精确还原。所有 token 已经在 `prototype/colors_and_type.css` 里定义好——**直接把这个文件的 `:root` 变量搬进 `frontend/app/globals.css` 即可**（见下方「主题令牌」）。

---

## 总体布局（App Shell）

替代现有 `BeeSwarmShell.tsx` 里 `maxWidth:1200; margin:auto` 的单列结构。新结构是**两栏全高 flex**：

```
┌──────────────┬─────────────────────────────────────────┐
│  RAIL 268px  │  MAIN (flex:1)                           │
│              │  ┌─ TOPBAR 60px (sticky, 毛玻璃) ──────┐ │
│  品牌        │  │ [场景切换 ▾]      ☀ 🔔 ?            │ │
│  [+ 新咨询]  │  ├──────────────────────────────────────┤ │
│              │  │  SCROLL (居中列 max-width 768px)     │ │
│  最近 ──────  │  │   · 用户气泡（右对齐）               │ │
│   · 会话1    │  │   · AI 回答（左侧光点头像 + 全宽）   │ │
│   · 会话2    │  │       - 顾问团协作条（可折叠）        │ │
│   ...        │  │       - 建议正文 + 分步              │ │
│              │  │       - KPI 指标条                   │ │
│  ──────────  │  │       - 红队风险提示                 │ │
│  切换场景    │  │       - 各顾问发言（折叠）           │ │
│  看协作      │  │       - 操作条（复制/重答/👍👎）     │ │
│  设置        │  ├──────────────────────────────────────┤ │
│  [头像] 柯岚 │  │  COMPOSER (absolute bottom, 渐隐底)  │ │
└──────────────┴─────────────────────────────────────────┘
```

- 整体：`display:flex; height:100vh; overflow:hidden`。
- 居中对话列 `max-width: 768px`（变量 `--col`），左右 `padding: 24px`。
- 输入框 **常驻底部**（`position:absolute; bottom:0`），上方加 `linear-gradient(to top, var(--bg-app) 58%, transparent)` 让内容滚动时自然淡出。
- 移动端（`max-width:880px`）：侧栏变为覆盖式抽屉（`position:absolute; z-index:40` + 阴影），顶栏左侧出现汉堡按钮。

---

## 屏幕 / 视图

应用是**单页对话式**，有两个状态（互斥切换，对应原型 `showWelcome()` / `showThread()`）：

### 1. Welcome / 欢迎空状态
- **用途**：没有进行中的对话时（点「新咨询」后）的着陆页。
- **布局**：居中列，垂直居中（`justify-content:center`，顶部 `padding-top:7vh`）。
- **组件**：
  - 大标题「你好，**柯岚**」——`你好，` 用 `--fg-1`，名字用 `--gradient-brand` 做 `background-clip:text` 渐变字。字号 `clamp(30px,4.4vw,46px)`，weight 600，`letter-spacing:-0.025em`。
  - 副标题：`--text-body-lg`，`--fg-2`，最大宽 540px。
  - **建议卡片** 2×2 网格（`gap:12px`）：每张卡 = Material 图标（`--accent`）+ 文案。卡片 `--bg-surface` / `--radius-lg` / 1px `--border-1` / `--shadow-xs`；hover 抬升 `translateY(-2px)` + `--shadow-md`。文案见下方 Copy。
  - 下方紧跟 Composer（同一个组件，inline 形态）。

### 2. Thread / 对话流
- **用途**：发起咨询后的主界面；显示一问一答，可多轮。
- **布局**：居中列，`padding-bottom:160px`（给底部 composer 留白），turn 之间 `gap:30px`。
- 每个 turn 含一条用户消息 + 一条 AI 回答（见下「组件细节」）。

> **默认落地**：原型加载时直接渲染一条**已完成的对话**（`showThreadDemo()`），方便审稿。真实应用里：有进行中/历史会话则进 Thread，否则进 Welcome。

---

## 组件细节（逐个还原）

### A. 侧栏 Rail（新增；现无对应组件，建议抽 `Sidebar.tsx`）
- 宽 268px，`--bg-surface`，右侧 1px `--border-1`，全高 flex 列。
- **品牌区**：34×34 圆角方块（`--radius-md`），填 `--gradient-brand`，内白色 `diversity_3` 图标，阴影 `0 3px 10px rgba(31,102,230,.32)`。右侧「智囊团」(600/17px) + 副标「H-SEMAS · 多智能体顾问」(`--fg-3`)。最右收起按钮 `left_panel_close`。
- **新咨询按钮**：pill（`--radius-pill`），1px `--border-2`，`--bg-surface`，`add` 图标 + 文字。hover → `--bg-accent-soft` 底 + `--border-accent` 边 + `--accent` 字 + 抬升。映射原 `setMode`/清空 → 新会话。
- **「最近」列表**：来自 `GET /api/memory/{mode}`（现有 `HistoryPanel` 的数据）。每行 = 26×26 圆角图标块 + 标题（单行省略）+ 元信息（场景 · N 位顾问）。选中行 `--bg-accent-soft` 底、图标块变 `--accent` 实心、标题变 `--accent`。
- **底部**：三个 foot-item（切换场景·顾问团 / 看顾问怎么协作 / 设置）→ 分别打开 `SettingsDrawer`（initialTab `scenario`）、`SwarmDashboardModal`、`SettingsDrawer`。最底用户行：30×30 渐变头像 + 名字 + 「高档脑子·旗舰」（对应现有 `tier` 状态）。

### B. 顶栏 Topbar
- 高 60px，`background: color-mix(in srgb, var(--bg-app) 78%, transparent)` + `backdrop-filter: blur(14px)`，sticky。
- **左**：场景切换 pill（替代现有 `ScenarioDropdown`）。结构 = 28×28 图标块（`--bg-accent-soft` 底、`--accent` 图标）+ 两行文字（场景名 600/14、hint 500/10.5 `--fg-3`）+ `expand_more`。点击弹出场景选择浮层（见 F）。映射 `mode` / `setMode`。
- **右**：三个 40×40 ghost 图标按钮——`dark_mode`（主题切换，映射现有 `toggleTheme`）、`notifications`（带 `--accent` 小红点，映射 `NotificationBell`）、`help`。

### C. 用户消息气泡
- 右对齐。`max-width:80%`，`--bg-accent-soft` 底，`--fg-1` 字，圆角 `22px 22px 6px 22px`，padding `13px 18px`，`--text-body-lg`，`--shadow-xs`。
- 附件（图片/文档）渲染为下方 att-chip 行（对应现有 `images`/`docFiles` + `ImageStrip`）。

### D. AI 回答（核心；重写 `ResultPanel.tsx` 的视觉）
左侧 34×34 渐变「光点」头像（`auto_awesome` 实心白），右侧全宽 body，`gap:16px`：

1. **顾问团协作条 `.swarm`**（这是签名元素，替代原 emoji 文字 + `SwarmDashboardModal` 的入口）：
   - 卡片 `--bg-surface` / `--radius-lg` / 1px `--border-1`。
   - 头部一行（可点击折叠）：左侧状态图标（运行中 `progress_activity` 旋转；完成 `check_circle` `--success`）+ 标题 + `expand_more` 雪佛龙（展开转 180°）。
   - 完成态标题：`<b>5 位顾问</b>已完成协作 · CEO 分诊 → 并行讨论 2 轮 → 综合`（`<b>` 用 `--accent`）。
   - 展开区：① **步骤时间线**（4 步：分诊官读题 / N 位顾问并行讨论 / 红队挑刺 / 分诊官综合），每步 18×18 圆 pip（完成 `--success-bg` + `check`）。② **顾问网格**（`repeat(auto-fill,minmax(150px,1fr))`）：每个顾问 28×28 彩色圆头像（首字，色板见 tokens）+ 名字 + 4px 自信度进度条（`--accent` 填充）+ 右侧百分比。
   - **运行态动画**（对应现有 WebSocket 事件，见「交互」）：顾问从 `idle`(opacity .5) → `thinking`（头像 `pulse` 脉冲、边框 `--border-accent`、状态字「思考中」）→ 完成（进度条按 `confidence_score` 充能、显示百分比）。

2. **建议正文 `.answer`**（对应 `ceo_decision`）：
   - 引导段 `.lead`：`--text-body-lg`、`--fg-1`；`<strong>` 加粗 `--fg-1`。
   - 小标题 `h4`：600/15px + 前置 `--accent` 图标（如 `format_list_numbered`）。
   - **分步列表**：每步左侧 26×26 圆形序号（`--bg-accent-soft` 底 + `--accent` + JetBrains Mono，CSS counter 自增），右侧 `--text-body-lg` 文字。
   - 现有的 `SmartResultRenderer`（markdown 渲染）可继续用于真实正文；本设计定义的是它的**容器排版与配色**。

3. **KPI 指标条 `.kpis`**（对应现有 `KPICard`/`KPIRow`，去成本）：横排 flex，每个 = 图标 + 数值（17px JetBrains Mono）+ 标签（11.5px `--fg-3`）。四个：位顾问参与 / 平均共识度 / 意见分歧 / 红队风险。图标按 tone 着色：`good`=`--success`、`warn`=`--warning`、`bad`=`--danger`、`accent`=`--accent`。数据来自 `dept_reports` 的 `confidence_score`、`dissent_intensity`、`red_team_risks.length`。

4. **红队风险提示 `.callout.warn`**（对应 `red_team_risks`）：`--warning-bg` 底，`color-mix(--warning 32%)` 边，`--radius-lg`。标题 `gpp_maybe` 图标 + 「红队提醒：这些地方要小心」。每条风险 `chevron_right` 图标 + 文字，条目间淡 warning 分隔线。

5. **各顾问发言折叠 `.accord`**（对应 `dept_reports`）：卡片头（`forum` 图标 + 「各顾问具体怎么说」+ 「N 份发言」+ 雪佛龙）。展开后每个部门一张 dept 卡：彩色头像 + 部门名 + 右侧自信度药丸（颜色按 `confColor()`：≥.8 绿 / ≥.65 琥珀 / 否则红，底色用对应 `*-bg`）+ 发言正文 + 可选「⚡ 分歧」分隔块（`conflicts`，对应现有 `r.conflicts`）。保留现有「🔄 重跑此部门」按钮逻辑（`onRerunDept`），样式改为本系统的次要按钮。

6. **操作条 `.actions`**：36×36 ghost 按钮——复制 / 重新生成 / 分享 / 分隔线 / 👍 / 👎。👍👎 映射现有 `onFeedback(reward)`（bandit 学习）；选中态 `on-up`(`--success` + `--success-bg`) / `on-down`(`--danger` + `--danger-bg`)。最右元信息：`schedule` 图标 + `elapsed_sec` + 「努力程度 X」。

### E. 输入框 Composer（替代现有 `TaskInput` + 「开始」按钮 + `DifficultySlider`）
- 外框 `.comp-box`：1px `--border-2`、`--bg-surface`、`border-radius:28px`、`--shadow-md`；focus-within 时边框变 `--border-accent` + `--shadow-lg` + 4px `--accent-ring` 光环。
- 内部：自适应高度 `<textarea>`（max 170px）；底部一行 = 加附件圆钮（`add_circle`）、「努力程度」标签、**努力程度分段控件**、发送钮。
- **努力程度分段控件**（替代 `DifficultySlider`，去掉成本标签）：pill 容器内 4 个段（简单/一般/深入/全力），每段前置小圆点。选中段 `--bg-surface` 底 + `--shadow-xs`，文字色按档位：简单=`--success`、一般=`--accent`、深入=`--warning`、全力=`--danger`。映射现有 `difficulty` 1–4 + `runByEffort` 的 `effort→(route,rounds)` 表。
- **发送钮**：42×42 圆。空输入时灰（`--gray-200`/暗色 `--bg-active` + `--fg-4`）；有内容 `.ready` → `--accent` 底 + 白 `arrow_upward` + `--shadow-accent`，active 时 `scale(.94)`。
- 提示行：`bolt` 图标 + 「『深入』会让 5 位顾问并行讨论 2 轮 · 回车发送，Shift+回车换行」。
- 回车发送、Shift+回车换行（对应原型 keydown 逻辑）。

### F. 场景选择浮层 `.pop`（替代 `ModePicker` 弹层）
- `--bg-surface` / `--radius-lg` / `--shadow-lg`，内部可滚（max-height 340）。每项 = 30×30 图标块 + 两行（场景名 + hint）+ 选中打勾。选中项 `--bg-accent-soft` 底、图标块 `--accent` 实心。
- 13 个内置场景及其 Material 图标见下「场景图标映射」（对应 `BUILTIN_MODES`）。

---

### G. 设置页 `showSettings`（替代 `SettingsDrawer`，建议抽 `SettingsPage.tsx`）

居中 760px 单列，顶部 `.page-head` = 44px 圆形返回钮（`--shadow-sm`）+ 标题（27px/600）+ 副标。下分若干 `.set-group`，每组一个小标题（`.set-group-h`，11px 大写 + `--accent` 图标）+ 一张 `.set-card`（圆角 20 / 弥散 `--shadow-sm`，行间 1px `--divider`）。每行 `.set-row` = 40px 圆角图标块（`--bg-accent-soft`/`--accent`）+ 主副文案 + 右侧控件。控件三种：

- **分段控件 `.seg`**：pill 容器，选中段 `--bg-surface` + `--shadow-xs` + `--accent` 字。用于主题、默认努力程度、讨论轮数。
- **开关 `.switch`**：50×30 pill，`on` 时 `--accent` + 圆点右移 20px。用于通知项、记忆历史。
- **导航行 `navRow`**：右侧值文字 + `chevron_right`，整行可点。危险项用 `.set-ico.danger`（`--danger-bg`/`--danger`）。

分组内容（映射现有设置）：① **外观**——主题（浅色/深色/系统，调 `setTheme`）、强调色（3–4 色板，写 `--accent`）；② **顾问与讨论**——默认场景（→ 场景浮层）、默认努力程度（1–4，映射 `difficulty`）、讨论轮数（映射 `effort→rounds`）；③ **脑子档位**——3 张 `.tier` 卡（标准/高档/旗舰，映射现有 `tier`，选中 `--accent` 边 + `--bg-accent-soft`）；④ **通知**——咨询完成/红队高风险/每周回顾开关；⑤ **隐私与数据**——记忆历史开关（映射 `/api/memory` 开关）、导出数据、清除所有会话（危险）；⑥ **关于**——版本/帮助/反馈。

### H. 个人页 `showProfile`（新增 `ProfilePage.tsx`）

同 760px 单列。顶部 `.prof-hero`：`--gradient-brand-soft` 背景圆角卡，72px squircle 渐变头像 + 姓名（24px）+ 邮箱 + `.prof-badge` 会员药丸（`--accent` 边 + `diamond` 图标，映射 `tier`）。下方 `.stat-grid` 三张统计卡（本月咨询 / 顾问调用 / 平均共识度，数值用 JetBrains Mono 26px，趋势用 `--success`）——数据来自 `/api/memory` 聚合。再下 **最常请教的顾问**（头像 + 名称 + `.fav-bar` 进度条 + 百分比，从历史 `dept_reports` 频次统计）。最后 **账户**组：偏好设置（→ 设置页）、切换账号、退出登录（危险）。

入口：侧栏底部用户行点击 → `showProfile`；侧栏「设置」→ `showSettings`。进入页面时隐藏顶栏场景 pill，返回钮回到上一视图。

---

## 交互与行为

- **发送任务**（`submit`）：append 用户气泡 → append AI turn（先只含运行态 `.swarm`）→ 平滑滚到底 → 跑 `runDeliberation` 动画 → 动画结束后用 `buildAnswer` 渲染完整回答替换 body。
  真实应用里，动画**由后端 WebSocket 事件驱动**，而非定时器：
  | 现有事件 (`BeeSwarmShell.attachStream`) | UI 动作 |
  |---|---|
  | `dispatcher_ready` | 协作条出现，标题「分诊官正在分配顾问…」，步骤1 完成 |
  | `fanout_started`（payload.depts） | 按 depts 生成顾问网格（idle），标题转「顾问们正在并行讨论…」，步骤2 进行中 |
  | `dept_done`（payload.dept, consensus, confidence） | 对应顾问 `thinking→done`，进度条按 confidence 充能 |
  | `debate_converged` | 步骤3（红队）完成 |
  | `decision_done`（summary） | 旋转图标→`check_circle`，渲染完整回答（KPI/风险/部门/操作条），步骤4 完成 |
  | `ws.onerror` | 顶部/气泡内显示错误（现有 `setError`） |
- **新咨询**（`newConsult`）：清空 thread + 取消选中 → 进 Welcome。
- **切换场景**（`setScene`）：更新顶栏标题/hint/图标 + `setMode(id)`；真实应用应同时刷新「最近」列表。
- **主题切换**：`document.documentElement.setAttribute("data-theme", ...)`，图标 `dark_mode`↔`light_mode`，写入 localStorage（沿用现有 `h-semas:theme`，注意 SSR：初值固定、`useEffect` 里读 localStorage，避免 hydration 报错——仓库已有此坑的处理）。
- **折叠交互**：协作条、各顾问发言、场景浮层均为点击切换 `.open`，雪佛龙 180° 旋转。
- 所有过渡 120–320ms，`--ease-out`（入场）/ `--ease-in-out`（移动）。尊重 `prefers-reduced-motion`（原型已加 media query）。

## State Management（基本沿用现有，不新增数据流）

复用 `BeeSwarmShell` 既有状态：`mode`、`task`、`difficulty`、`busy`、`summary`、`history`、`heats`、`progress`、`tier`、`images`、`docFiles`、`theme`、`currentDecisionId`、`runMeta`。本次只是把它们**重新绑定到新组件**。建议新增：
- `view: "welcome" | "thread"`（替代当前直接渲染）。
- `turns: Turn[]`（对话历史数组，支持多轮上屏；每个 turn 持 `{ user, summary? }`）。
- 协作条所需的 per-advisor 状态从现有 `heats`（`DeptHeat[]`：`dept/heat/status/confidence`）派生即可。

## Design Tokens

**全部来自 `prototype/colors_and_type.css`——把它的 `:root` 块整体复制到 `frontend/app/globals.css`。** 关键值（hex）：

**色彩**
- 主色 Clarity Blue：`--accent #1F66E6`（`-hover #1A53BE`，`-press #184696`）
- 中性冷灰（承载 95% UI）：`#FFFFFF / #FBFCFE(bg-app) / #F4F7FB / E9EEF6 / DCE3ED / C4CDD9 / 9AA5B4 / 6B7686 / 4D5765 / 373F4B / 252B34 / 171B21`
- 语义：success `#14834F`（bg `#E7F5EE`）、warning `#B47A00`（bg `#FBF1DD`）、danger `#C42E27`（bg `#FCEBEA`）
- 文字：`--fg-1 #171B21 / --fg-2 #4D5765 / --fg-3 #6B7686 / --fg-4 #9AA5B4`
- 选中/浅蓝面：`--bg-accent-soft #EEF4FF`
- 品牌渐变（仅 AI/spark 场景，勿做整屏背景）：`linear-gradient(135deg,#1F66E6 0%,#4C9AF5 48%,#8E7BF0 100%)`
- 顾问头像色板：`["#1F66E6","#8E7BF0","#1E9E63","#E0A11A","#3B73F0","#5E8DFA","#14834F"]`（按 index 取模）

**字体**
- 全部 UI：`Lexend`（CJK 回退 `"PingFang SC","Hiragino Sans GB","Microsoft YaHei",system-ui`）。数字/统计：`JetBrains Mono`。
- 标题 `letter-spacing:-0.02em` + `text-wrap:balance`；正文 `text-wrap:pretty`。
- 取自 Google Fonts CDN（link 标签见原型 `<head>`）。

**间距 / 圆角 / 阴影 / 动效**：4px 基（`--space-1..24`）；圆角 控件 14 / 卡片 20 / 大面 28 / pill 999 / 小 chip 10；`--ease-out` `cubic-bezier(.2,.7,.3,1)`，时长 120/200/320ms。

**⭐ 弥散阴影（Gemini 风，覆盖原硬阴影）**：卡片/浮层不再用生硬投影，改用**大模糊、低透明、冷蓝调**的弥散阴影。**请用下面这套覆盖 `globals.css` 里的 `--shadow-*`**（也就是 `prototype/colors_and_type.css` 已更新的值）：
```css
html[data-theme="light"]{
  --shadow-xs:0 1px 2px rgba(28,52,102,.05), 0 1px 1px rgba(28,52,102,.03);
  --shadow-sm:0 4px 16px -4px rgba(28,52,102,.10), 0 1px 4px rgba(28,52,102,.05);
  --shadow-md:0 12px 34px -8px rgba(28,52,102,.13), 0 3px 12px -2px rgba(28,52,102,.07);
  --shadow-lg:0 28px 64px -14px rgba(28,52,102,.18), 0 10px 28px -8px rgba(28,52,102,.10);
  --glow:color-mix(in srgb, var(--accent) 14%, transparent); /* 品牌色发光，用于 spark/send */
}
```
要点：负 spread（`-Npx`）让阴影只在下方扩散、不外溢成硬边；色相用冷蓝 `rgba(28,52,102,…)` 而非纯黑，透明度压到 5–18%。深色主题同理用大模糊低透明的黑。**所有卡片（建议卡、KPI、协作条、部门折叠、浮层、输入框）一律走这套 token，不要再写一次性的 `box-shadow`。**

**⭐ Gemini 图标按钮规范（外圈大、内容小）**：所有圆形图标按钮 = **更大的圆形点击区 + 更小的居中字形**。
- 顶栏图标按钮（主题/通知/帮助）：**44px 白色圆**（`--bg-surface`）+ `--shadow-sm` 弥散阴影，**字形仅 21px**；hover 抬升 1px + `--shadow-md`。即「浮在浅底上的白色圆按钮」。
- 侧栏图标按钮：40px 圆、字形 20px。
- 场景/标签图标块：留更多内边距——容器 32×32、字形 18px（约 56% 填充）。
- 发送钮：44px 圆，就绪态 `--accent` + `--glow` 发光，字形 21px。
- 通用比例：**字形占圆直径 ≈ 45–50%**，不要塞满。命中区始终 ≥44px。

**⭐ AI「光点」头像 = 圆角方块（squircle）**：参考 Gemini 最新版，AI 头像不是正圆，而是**蓝色圆角方块**——36×36、`border-radius:13px`、填 `--gradient-brand`、带 `0 5px 16px -4px var(--glow)` 发光、内含一个**小号**白色 spark（18px）。小尺寸版 28px / radius 10 / 字形 14。

**⭐ 蓝色弥散背景**：欢迎页底部加一层 Gemini 式柔和蓝光晕（径向渐变 `--accent` 16% → 透明，`filter:blur(8px)`，置于内容之下 `z-index:-1`）。见原型 `.welcome::after`。

**深色主题**：原型 `html[data-theme="dark"]` 覆盖了一套冷黑灰令牌（`--bg-app #0F1115` 等），直接搬运。保留应用原有的深色为默认的传统也可以——令牌层让一处切换。

## ⭐ 卡片 / 间距 / 字号标准（iOS 向 — v4 更新）

这一版把"卡片显硬"和"字偏小"两个问题按 iOS 最新风格统一收口，**新建任何卡片 / 列表 / 屏幕都按这套来**：

### 1. 柔和浮起卡（杜绝"硬边框 + 投影"组合）
之前卡片"生硬"的根因是 **1px 实线 `--border-1` + 投影**叠加，边缘发硬。新规则：
- **特征卡 / 主卡**（如推荐卡、streak 卡、统计卡）：**无边框**，仅靠弥散阴影（`--shadow-md` 浮起感 / `--shadow-sm` 轻浮起）与背景分离 —— 即 Gemini / iOS 的"浮起纸片"。
- **列表行 / 密集卡**（如习惯行、设置行）：用**最浅的发丝线 `--divider`**（不是 `--border-1`）+ `--shadow-xs/sm`，保留分隔感但不发硬。
- **渐变卡**（AI / 高亮，如进度卡）：`--gradient-brand-soft` 背景，**无边框无阴影**，靠色块自然分隔。
- 一句话：**`--border-1` 不再与阴影同时用在卡片上**；要边框就用 `--divider`，要分离优先用弥散阴影。

### 2. 间距（iOS 分组留白）
- **屏幕水平内边距**：20–22px。
- **卡片内边距**：主卡 18–20px；列表行 15–16px（行高更松）。
- **列表行之间**：10–11px（原 8 太挤）。
- **分组之间（section ↔ section）**：26–28px 大留白（原 18），分组小标题与首卡间距 11–12px。
- **圆角**：列表行 / 中卡 18；大卡 / 渐变卡 20–22；底部 sheet 28。

### 3. 字号（放大；"大一点没有错"）
对照 iOS 文本层级整体上调，最小正文不低于 14.5px：

| 角色 | 旧 | 新 | 用例 |
|---|---|---|---|
| 大标题 (Large Title) | 30 | **33** /1.08 600 | 屏幕问候、Insights、设置页标题 27 |
| 卡片标题 | 17 | **18.5** 600 | "3 of 5 done" |
| 列表项标题 | 15 | **16.5** 500 | 习惯名、设置项 ≥15.5 |
| 正文 / 说明 | 13 | **14.5–16** | 卡片副文、聊天气泡 16 |
| 统计数字 (mono) | 24 | **27** 600 | streak / 一致性 / KPI 19–26 |
| 次级 / 元信息 | 11–12 | **12.5** | 分组标签、行内 meta |
| 标签栏文字 | 11 | **11.5** | TabBar |

> 这套标准已落进 Jim Clear 手机 UI kit（`ui_kits/app/*`，TodayScreen / Habits / HabitDetail / AskJim / AddHabit / Insights / Primitives）与 H-SEMAS 覆盖层；改造真实项目时一并对齐。

## 场景图标映射（Material Symbols Rounded，替代 emoji）

| mode_id | 标签 | 图标 |
|---|---|---|
| family_doctor | 家庭医生 | `stethoscope` |
| nutrition_fitness | 营养健身 | `fitness_center` |
| dining_recommendation | 餐饮推荐 | `restaurant` |
| purchase_decision | 采购决策 | `shopping_cart` |
| travel_planning | 旅行计划 | `flight` |
| child_education | 儿童教育 | `child_care` |
| legal_consulting | 法律咨询 | `gavel` |
| tax_insurance | 税务保险 | `account_balance` |
| learning_planning | 学习规划 | `school` |
| startup_advisory | 创业咨询 | `rocket_launch` |
| stock_trading | 股票交易 | `trending_up` |
| program_management | 程序管理 | `code` |
| generic_consulting | 通用咨询 | `lightbulb` |

**图标规范（Jim Clear × Gemini）**：Material Symbols **Rounded**，rest 态 outline（FILL 0）/ `--fg-3`，选中态 filled（FILL 1）/ `--accent`。**按上面「Gemini 图标按钮规范」处理外圈与字形比例**：圆形按钮外圈放大、内部字形缩小到直径的约 45–50%，命中区 ≥44px。**全程不用 emoji。**

## Copy（原型用到的文案，可直接复用）

- 欢迎副标题：「把你正在纠结的事写下来。我会先分诊，再请这套场景里最合适的几位顾问一起讨论，给你一个能落地的答案。」
- 输入框 placeholder：「把你的问题写清楚一点，顾问们会更准…」
- 努力程度提示：「『深入』会让 5 位顾问并行讨论 2 轮 · 回车发送，Shift+回车换行」
- 建议卡片（家庭医生场景示例）：失眠调作息 / 尿酸偏高怎么吃 / 孩子反复发烧何时就医 / 久坐腰酸缓解。
- 协作条完成态、KPI 标签、红队提醒标题等，见原型 `DEMO` 对象。

> 演示正文（失眠方案）只是占位示意，真实运行时由模型生成；请实现**排版与配色容器**，正文交给 `SmartResultRenderer` / 后端。

## 涉及的现有文件（改造清单）

| 现有文件 | 改造内容 |
|---|---|
| `frontend/app/globals.css` | 粘入 Jim Clear `:root` 令牌 **＋ `:root[data-theme="dark"]` 整套深色令牌 ＋ 弥散 `--shadow-*`**；引入 Lexend / JetBrains Mono / Material Symbols Rounded 的 `<link>`（在 `app/layout.tsx` 的 `<head>`，`layout.tsx` 已是 `data-theme="light"`）。 |
| `frontend/components/v2/BeeSwarmShell.tsx` | 重排为「侧栏 + 顶栏 + 对话流 + 底部 composer」；新增 `view`/`turns` 状态；移除内联深色硬编码改用令牌。现有 `theme` light/dark（`h-semas:theme`）扩展为浅/深/系统三档。 |
| 新增 `Sidebar.tsx`（仓库已有同名组件，套新样式即可） | 品牌 + 新咨询 + 最近列表 + 底部菜单；底部用户行点击 → 个人页。 |
| **新增 `SettingsPage.tsx`** | 替代 / 收编 `SettingsDrawer` + `UserMemoryPanel`：外观（主题/强调色）、顾问与讨论、脑子档位（`tier` A=标准/B=高档/C=旗舰）、通知、隐私与数据（`/api/user-profile`、`/api/memory`）、关于。规范见「设置页 §G」。 |
| **新增 `ProfilePage.tsx`** | 个人页：会员卡 + 统计 + 常用顾问 + 账户。数据聚合 `/api/memory`、`/api/user-profile`。规范见「个人页 §H」。 |
| `ScenarioDropdown.tsx` / `ModePicker.tsx` | 顶栏场景 pill + `.pop` 浮层；emoji → Material 图标。 |
| `TaskInput.tsx` + `DifficultySlider.tsx` | 合并为 Gemini 式 `Composer`（圆角框 + 分段努力程度 + 发送钮，去成本标签）。 |
| `ResultPanel.tsx`（含 `viz/KPICard`、`MiniBarChart`、`Timeline`、`InfoFeed`、`SmartResultRenderer`） | 套用 swarm 协作条 / lead+分步 / KPI chips / 风险 callout / 部门折叠 / 操作条；保留 `onRerunDept`、`onFeedback`。 |
| `SwarmDashboardModal.tsx` | 进行态动画并入对话内的协作条（也可保留弹窗作为「看协作」详情）。 |
| `HistoryPanel.tsx` | 数据迁入侧栏「最近」列表。 |
| `NotificationBell` / `LogsPanel` / `SettingsDrawer` | 顶栏/侧栏入口，套新按钮样式，逻辑不动。 |

## Files（本包内容）

- `prototype/index.html` —— 高保真交互原型（含 Welcome / Thread 两态、协作条动画、完整回答）。在浏览器直接打开即可；图标走 Google Fonts CDN（需联网；某些截图工具不渲染图标字体属正常）。
- `prototype/standalone-offline.html` —— 同一原型的**离线自包含版**（字体/样式全部内联，断网也能开）。给不方便联网的同事看、或想自己截图时用这个。
- `prototype/colors_and_type.css` —— Jim Clear 全量设计令牌（颜色 / 字体 / 间距 / 圆角 / 阴影 / 动效）+ 语义 class。**改造时把它的 `:root` 直接搬进 `globals.css`。**
- `screenshots/` —— 参考图：
  - `01-overview.png` —— 对话流顶部：场景顶栏 + 用户气泡 + 顾问团协作条。
  - `02-welcome.png` —— 欢迎空状态：渐变问候 + 建议卡片 + 输入框。
  - `03-recommendation.png` —— AI 回答正文：引导段 + 分步建议。
  - `04-advisors-and-risk.png` —— 红队风险提示 + 各顾问发言折叠（自信度药丸）。
  - `05-settings.png` —— 设置页（外观 / 顾问与讨论 / 脑子档位 …）。
  - `06-profile.png` —— 个人页（会员卡 + 统计 + 常用顾问）。
  - `07-dark-mode.png` —— 深色模式下的设置页。
  - `08-showcase-dark.png` —— 设计系统 Showcase 的深色模式。
  > 注：截图工具对图标字体的渲染偶有缺失，**以两个 HTML 原型在真实浏览器里的呈现为准**。

## 注意

- **只换皮 + 重排，不动决策链路**：所有 `/api/*`、WebSocket、bandit 反馈、mode 隔离逻辑保持现状。
- **SSR/hydration**：主题、tier 等读 localStorage 必须放 `useEffect`，初值与服务端一致（仓库已有同类处理，照搬）。
- **无障碍**：图标按钮加 `aria-label`/`title`；命中区 ≥44px；`prefers-reduced-motion` 降级动画。
- 字体经环境验证可正常加载（`document.fonts.check("24px 'Material Symbols Rounded'") === true`）。
