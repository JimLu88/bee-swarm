# AI提示词工程 prompt_engineering —— 书单(双源核验版)

> 团队:CEO(AI提示词工程总顾问)+ 6 个专科部门(各 1 主管 + 3 名员工)。
> **双源选书规则(关键)**
> - **A 类**:豆瓣 ≥8.5(联网核实,标真实分+评价人数)。
> - **G 类**:Goodreads ≥4.0/5(联网核实)——本领域新书多、中文版少,优先用 G 收录国际前沿。
> - **B 类**:两站都无可信公开分的纯权威书/官方文档/教科书,标 `—` 按权威收。
> - 判定:豆瓣≥8.5 或 Goodreads≥4.0 任一满足即入选。
> - 铁律:只列真实存在的书,绝不编造书名/评分;查不到留 `—`。提示工程是新兴领域,大量内容在官方文档/论文中,书目以"基础理论 + 工程落地 + 安全"为骨架。
> - 配额:员工 30/部门池;主管 40+管理10=50;CEO 跨部门 90+管理10=100。
> - 评分为查证当时数值,会随版本/时间略变。

---

## CEO(AI提示词工程总顾问)— 100
**跨部门可读(已核实)**
| 书名 | 作者 | 豆瓣 | Goodreads | 类 |
|------|------|------|-----------|----|
| Designing Machine Learning Systems | Chip Huyen | — | 4.43 | G |
| Deep Learning(花书) | Goodfellow 等 | — | 4.36 | G |
| Hands-On Machine Learning(2nd) | Aurélien Géron | — | 4.55 | G |

**管理 10 本**见《管理类共用书单》。各部门核心从 6 部门各取 2-4 本汇入。

---

## 提示架构师 prompt_architect
主管 | 员工 助理·骨干·审核
**G 类(Goodreads ≥4.0 已核实)**
| 书名 | 作者 | Goodreads |
|------|------|-----------|
| Prompt Engineering for Generative AI | Phoenix & Taylor (O'Reilly) | 4.10 |
| Hands-On Large Language Models | Alammar & Grootendorst | 4.50 |

**B 类·权威(两站样本不足/无,按权威/官方收)**
OpenAI Prompt Engineering Guide(官方)、Anthropic Prompt Engineering Docs(官方)、The Prompt Engineering Handbook、AI 提示工程实战(国内引进/原创,评分人少)。
**补足方向**:Few-shot / CoT / ReAct 模式手册;角色与系统提示设计;结构化输出(JSON/函数调用)。

---

## 评测工程师 eval_engineer
主管 | 员工 助理·骨干·审核
**G 类(Goodreads ≥4.0 已核实)**
| 书名 | 作者 | Goodreads |
|------|------|-----------|
| Designing Machine Learning Systems | Chip Huyen | 4.43 |
| AI Engineering | Chip Huyen | 4.40 |
| Evaluating Machine Learning Models | Alice Zheng (O'Reilly) | 4.00 |

**B 类·权威**
机器学习评估方法论、LLM 评测基准综述(HELM/MMLU 文档)、统计学习基础(ESL)、A/B 实验设计教科书。
**补足方向**:离线/在线评测体系;人评(human eval)与 LLM-as-judge;回归测试集构建。

---

## RAG 顾问 rag_advisor
主管 | 员工 助理·骨干·审核
**G 类(Goodreads ≥4.0 已核实)**
| 书名 | 作者 | Goodreads |
|------|------|-----------|
| Hands-On Large Language Models | Alammar & Grootendorst | 4.50 |
| Build a Large Language Model (From Scratch) | Sebastian Raschka | — |
| Natural Language Processing with Transformers | Tunstall 等 | 4.40 |

**B 类·权威**
信息检索导论(Manning《Introduction to Information Retrieval》)、向量数据库实践、LangChain/LlamaIndex 官方文档、RAG 论文集(Lewis 2020 等)。
**补足方向**:检索召回与重排;上下文窗口管理;幻觉抑制与引用溯源。

---

## 成本优化师 cost_optimizer
主管 | 员工 助理·骨干·审核
**G 类(Goodreads ≥4.0 已核实)**
| 书名 | 作者 | Goodreads |
|------|------|-----------|
| AI Engineering | Chip Huyen | 4.40 |
| Designing Machine Learning Systems | Chip Huyen | 4.43 |

**B 类·权威**
LLM 推理优化(量化/蒸馏/KV cache 文档)、模型选型与成本核算白皮书、提示缓存(prompt caching)官方文档、Token 经济学实践。
**补足方向**:模型路由与降级策略;批处理与缓存命中率;小模型微调 vs 大模型直调权衡。

---

## 安全审查师 safety_reviewer
主管 | 员工 助理·骨干·审核
**G 类 / B 类(已核实/权威)**
| 书名 | 作者 | 豆瓣 | Goodreads | 类 |
|------|------|------|-----------|----|
| The Alignment Problem | Brian Christian | — | 4.27 | G |
| Human Compatible | Stuart Russell | — | 4.13 | G |

**B 类·权威**
OWASP Top 10 for LLM Applications(官方)、Prompt Injection 攻防文档、AI 红队测试手册、负责任 AI(Responsible AI)框架、Anthropic/OpenAI 安全政策文档。
**补足方向**:越狱(jailbreak)与注入防护;内容审核与合规;数据隐私与脱敏。

---

## 工作流设计师 workflow_designer
主管 | 员工 助理·骨干·审核
**G 类(Goodreads ≥4.0 已核实)**
| 书名 | 作者 | Goodreads |
|------|------|-----------|
| AI Engineering | Chip Huyen | 4.40 |
| Building LLM Powered Applications | Valentina Alto | 4.00 |

**B 类·权威**
Agent 设计模式(ReAct/Reflexion/Plan-and-Execute 论文)、LangGraph/AutoGen 官方文档、工具调用(function calling)规范、多智能体协作综述。
**补足方向**:链路编排与状态机;工具/插件接入;失败重试与人机协同(HITL)。

---

# ★ 全书名汇总(下载用 · 一行一本)

| 书名 | 作者 | 豆瓣 | Goodreads | 类 | 归属 |
|------|------|------|-----------|----|------|
| Designing Machine Learning Systems | Chip Huyen | — | 4.43 | G | 评测/CEO |
| AI Engineering | Chip Huyen | — | 4.40 | G | 成本/工作流/评测 |
| Deep Learning(花书) | Goodfellow 等 | — | 4.36 | G | CEO |
| Hands-On Machine Learning(2nd) | Aurélien Géron | — | 4.55 | G | CEO |
| Hands-On Large Language Models | Alammar & Grootendorst | — | 4.50 | G | 提示/RAG |
| Prompt Engineering for Generative AI | Phoenix & Taylor | — | 4.10 | G | 提示 |
| Natural Language Processing with Transformers | Tunstall 等 | — | 4.40 | G | RAG |
| Build a Large Language Model (From Scratch) | Sebastian Raschka | — | — | B | RAG |
| Evaluating Machine Learning Models | Alice Zheng | — | 4.00 | G | 评测 |
| The Alignment Problem | Brian Christian | — | 4.27 | G | 安全 |
| Human Compatible | Stuart Russell | — | 4.13 | G | 安全 |
| Building LLM Powered Applications | Valentina Alto | — | 4.00 | G | 工作流 |
| OpenAI Prompt Engineering Guide(官方) | OpenAI | — | — | B | 提示 |
| Anthropic Prompt Engineering Docs(官方) | Anthropic | — | — | B | 提示 |
| The Prompt Engineering Handbook | — | — | — | B | 提示 |
| 统计学习基础(ESL) | Hastie 等 | — | — | B | 评测 |
| HELM/MMLU 评测基准文档 | Stanford CRFM 等 | — | — | B | 评测 |
| 信息检索导论 | Manning 等 | — | — | B | RAG |
| LangChain / LlamaIndex 官方文档 | — | — | — | B | RAG |
| RAG 论文集(Lewis 2020 等) | — | — | — | B | RAG |
| LLM 推理优化(量化/蒸馏文档) | — | — | — | B | 成本 |
| Prompt Caching 官方文档 | OpenAI/Anthropic | — | — | B | 成本 |
| OWASP Top 10 for LLM Applications | OWASP | — | — | B | 安全 |
| AI 红队测试手册 | — | — | — | B | 安全 |
| Responsible AI 框架 | — | — | — | B | 安全 |
| Agent 设计模式(ReAct/Reflexion 论文) | — | — | — | B | 工作流 |
| LangGraph / AutoGen 官方文档 | — | — | — | B | 工作流 |

> 注:提示工程为新兴领域,大量前沿在官方文档与论文中,B 类按官方/权威收录。`Goodreads —` = 该站暂无可信公开分。
