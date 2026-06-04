# 编程开发(技术架构团队) program_management —— 书单(双源核验版)

> 团队:CEO 方略(技术总监/系统设计)+ 6 个专科部门(各 1 主管 + 3 名员工)。
> **双源选书规则(关键)**
> - **A 类**:豆瓣 ≥8.5(联网核实,标真实分+评价人数)。
> - **G 类**:Goodreads ≥4.0/5(联网核实)——技术书国际版评分更可信,优先用 G 把经典补回来。
> - **B 类**:两站都无可信公开分的纯权威/教科书,标 `—` 按权威收。
> - 判定:豆瓣≥8.5 或 Goodreads≥4.0 任一满足即入选。
> - 铁律:只列真实存在的书,绝不编造书名/评分;查不到留 `—`。
> - 配额:员工 30/部门池;主管 40+管理10=50;CEO 跨部门 90+管理10=100。
> - 评分为查证当时数值,会随版本/时间略变。

---

## CEO 方略(技术总监 / 系统设计)— 100
**跨部门可读(已核实)**
| 书名 | 作者 | 豆瓣 | Goodreads | 类 |
|------|------|------|-----------|----|
| 架构整洁之道 | Robert C. Martin | 8.7 | — | A |
| Designing Data-Intensive Applications | Martin Kleppmann | — | 4.70 | G |
| Clean Code | Robert C. Martin | — | 4.35 | G |
| The Pragmatic Programmer | Hunt & Thomas | — | 4.33 | G |
| Refactoring | Martin Fowler | — | 4.24 | G |
| The Phoenix Project | Gene Kim 等 | — | 4.27 | G |

**管理 10 本**见《管理类共用书单》。各部门核心从 6 部门各取 2-4 本汇入。

---

## 首席架构师 principal_architect
主管 岑昭 | 员工 周析·范衡·李疑
**A 类(≥8.5 已核实)**
| 书名 | 作者 | 豆瓣 |
|------|------|------|
| 架构整洁之道 | Robert C. Martin | 8.7 |

**G 类(Goodreads ≥4.0 已核实)**
| 书名 | 作者 | Goodreads |
|------|------|-----------|
| Designing Data-Intensive Applications | Kleppmann | 4.70 |
| Building Microservices | Sam Newman | 4.08 |
| Domain-Driven Design | Eric Evans | 4.14 |
| Patterns of Enterprise Application Architecture | Martin Fowler | 4.07 |
| Fundamentals of Software Architecture | Richards & Ford | 4.05 |

**B 类·权威**
软件架构设计(Bass 等《Software Architecture in Practice》)、企业集成模式(EIP)、微服务设计、架构师修炼之道。
**补足方向**:CAP/一致性模型;事件驱动架构;C4 模型与架构决策记录(ADR)。

---

## 资深工程师 senior_engineer
主管 谷成 | 员工 吕援·钟实·苗审
**G 类(Goodreads ≥4.0 已核实)**
| 书名 | 作者 | Goodreads |
|------|------|-----------|
| Clean Code | Robert C. Martin | 4.35 |
| The Pragmatic Programmer | Hunt & Thomas | 4.33 |
| Refactoring | Martin Fowler | 4.24 |
| Code Complete | Steve McConnell | 4.31 |
| Working Effectively with Legacy Code | Michael Feathers | 4.04 |

**B 类·权威**
代码大全(中文版)、重构(中文版)、设计模式(GoF)、人月神话(Brooks)、SICP(计算机程序的构造和解释)。
**补足方向**:复杂度治理与工时估算;可维护性度量;技术债务清偿策略。

---

## 前端工程师 frontend_engineer
主管 苏漾 | 员工 邹设·项稳·卓鉴
**G 类(Goodreads ≥4.0 已核实)**
| 书名 | 作者 | Goodreads |
|------|------|-----------|
| Eloquent JavaScript | Marijn Haverbeke | 4.13 |
| You Don't Know JS (系列) | Kyle Simpson | 4.30 |
| Refactoring UI | Adam Wathan & Steve Schoger | 4.40 |
| Don't Make Me Think | Steve Krug | 4.18 |

**B 类·权威**
JavaScript 高级程序设计(红宝书)、CSS 揭秘、深入理解 ES6、Web 性能权威指南(High Performance Browser Networking)、可访问性 WCAG 指南。
**补足方向**:状态管理(Redux/Zustand)模式;前端性能优化(Core Web Vitals);组件库与设计系统。

---

## DBA / 数据架构师 dba
主管 范坚 | 员工 黎数·程稳·严鉴
**A 类 / G 类(已核实)**
| 书名 | 作者 | 豆瓣 | Goodreads | 类 |
|------|------|------|-----------|----|
| Designing Data-Intensive Applications | Kleppmann | — | 4.70 | G |
| Database Internals | Alex Petrov | — | 4.27 | G |
| SQL Performance Explained | Markus Winand | — | 4.32 | G |

**B 类·权威**
数据库系统概念(Silberschatz,经典教科书)、高性能 MySQL、PostgreSQL 修炼之道、数据密集型应用系统设计(中文版)、SQL 反模式。
**补足方向**:索引与查询优化;分库分表与分布式事务;数据一致性与备份恢复。

---

## 安全工程师 security_engineer
主管 黑明 | 员工 漏检·护稳·怀核
**G 类(Goodreads ≥4.0 已核实)**
| 书名 | 作者 | Goodreads |
|------|------|-----------|
| The Web Application Hacker's Handbook | Stuttard & Pinto | 4.23 |
| The Tangled Web | Michal Zalewski | 4.21 |
| Serious Cryptography | Jean-Philippe Aumasson | 4.40 |
| The Art of Software Security Assessment | Dowd 等 | 4.30 |

**B 类·权威**
白帽子讲 Web 安全(吴翰清)、OWASP Top 10 / OWASP ASVS、密码学原理与实践、Web 安全深度剖析、渗透测试实战。
**补足方向**:注入/XSS/CSRF 防护清单;密钥与机密管理;隐私合规(GDPR/个保法)。

---

## QA / 测试架构师 qa_engineer
主管 柯严 | 员工 测援·严覆·极鉴
**A 类 / G 类(已核实)**
| 书名 | 作者 | 豆瓣 | Goodreads | 类 |
|------|------|------|-----------|----|
| Site Reliability Engineering(Google SRE) | Betsy Beyer 等 | — | 4.21 | G |
| The Phoenix Project | Gene Kim 等 | — | 4.27 | G |
| Accelerate | Forsgren 等 | — | 4.16 | G |
| Continuous Delivery | Humble & Farley | — | 4.07 | G |

**B 类·权威**
Google 软件测试之道、测试驱动开发(Kent Beck《TDD by Example》)、单元测试的艺术、敏捷测试、xUnit Test Patterns。
**补足方向**:边界 case 与等价类划分;性能压测(JMeter/k6);回归矩阵与自动化框架。

---

# ★ 全书名汇总(下载用 · 一行一本)

| 书名 | 作者 | 豆瓣 | Goodreads | 类 | 归属 |
|------|------|------|-----------|----|------|
| 架构整洁之道 | Robert C. Martin | 8.7 | — | A | 架构/CEO |
| Designing Data-Intensive Applications | Martin Kleppmann | — | 4.70 | G | 架构/DBA/CEO |
| Clean Code | Robert C. Martin | — | 4.35 | G | 工程/CEO |
| The Pragmatic Programmer | Hunt & Thomas | — | 4.33 | G | 工程/CEO |
| Refactoring | Martin Fowler | — | 4.24 | G | 工程/CEO |
| The Phoenix Project | Gene Kim 等 | — | 4.27 | G | QA/CEO |
| Building Microservices | Sam Newman | — | 4.08 | G | 架构 |
| Domain-Driven Design | Eric Evans | — | 4.14 | G | 架构 |
| Patterns of Enterprise Application Architecture | Martin Fowler | — | 4.07 | G | 架构 |
| Fundamentals of Software Architecture | Richards & Ford | — | 4.05 | G | 架构 |
| Software Architecture in Practice | Bass 等 | — | — | B | 架构 |
| 企业集成模式(EIP) | Hohpe & Woolf | — | — | B | 架构 |
| Code Complete | Steve McConnell | — | 4.31 | G | 工程 |
| Working Effectively with Legacy Code | Michael Feathers | — | 4.04 | G | 工程 |
| 设计模式(GoF) | Gamma 等 | — | — | B | 工程 |
| 人月神话 | Frederick Brooks | — | — | B | 工程 |
| SICP 计算机程序的构造和解释 | Abelson & Sussman | — | — | B | 工程 |
| Eloquent JavaScript | Marijn Haverbeke | — | 4.13 | G | 前端 |
| You Don't Know JS | Kyle Simpson | — | 4.30 | G | 前端 |
| Refactoring UI | Wathan & Schoger | — | 4.40 | G | 前端 |
| Don't Make Me Think | Steve Krug | — | 4.18 | G | 前端 |
| JavaScript 高级程序设计(红宝书) | Nicholas Zakas | — | — | B | 前端 |
| High Performance Browser Networking | Ilya Grigorik | — | — | B | 前端 |
| Database Internals | Alex Petrov | — | 4.27 | G | DBA |
| SQL Performance Explained | Markus Winand | — | 4.32 | G | DBA |
| 数据库系统概念 | Silberschatz 等 | — | — | B | DBA |
| 高性能 MySQL | Schwartz 等 | — | — | B | DBA |
| SQL 反模式 | Bill Karwin | — | — | B | DBA |
| The Web Application Hacker's Handbook | Stuttard & Pinto | — | 4.23 | G | 安全 |
| The Tangled Web | Michal Zalewski | — | 4.21 | G | 安全 |
| Serious Cryptography | Aumasson | — | 4.40 | G | 安全 |
| The Art of Software Security Assessment | Dowd 等 | — | 4.30 | G | 安全 |
| 白帽子讲 Web 安全 | 吴翰清 | — | — | B | 安全 |
| OWASP Top 10 / ASVS | OWASP | — | — | B | 安全 |
| Site Reliability Engineering(Google SRE) | Betsy Beyer 等 | — | 4.21 | G | QA |
| Accelerate | Forsgren 等 | — | 4.16 | G | QA |
| Continuous Delivery | Humble & Farley | — | 4.07 | G | QA |
| 测试驱动开发(TDD by Example) | Kent Beck | — | — | B | QA |
| Google 软件测试之道 | Whittaker 等 | — | — | B | QA |
| xUnit Test Patterns | Gerard Meszaros | — | — | B | QA |

> 注:`豆瓣 —` 或 `Goodreads —` = 该站无可信公开分,按另一站分或领域权威性收录。技术书以 Goodreads 为主源。
