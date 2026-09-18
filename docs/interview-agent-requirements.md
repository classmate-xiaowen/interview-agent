# 面试能力提升 Agent —— 需求文档

> 版本：v1.0
> 日期：2026-09-16
> 状态：需求评审稿（设计方向已确认，待细化实现计划）

---

## 1. 项目概述

### 1.1 背景
求职者在面试准备中存在三类痛点：
1. **经验无法沉淀**——面过的题、面试官风格、公司文化散落在记忆里，无法复用。
2. **缺乏针对性训练**——通用题库与自身背景、目标公司脱节，练习效率低。
3. **表达与简历暴露风险**——口头表达缺乏反馈；简历直接导入存在隐私泄露。

本产品是一个 **AI 面试教练 Agent**，围绕「沉淀 → 导入 → 对话 → 脱敏 → 训练」五步闭环，帮助用户体系化提升面试能力。

### 1.2 目标与范围
- **目标**：MVP 阶段打通「知识库 + RAG + Agent 对话」核心闭环，验证「基于个人历史面试数据 + 市场环境 + 用户画像的针对性模拟面试」是否真正有效、好用。
- **范围**：本期需求文档覆盖全部 5 大功能，但明确分期（见第 9 节）。MVP 仅含 ①②③。

### 1.3 关键决策（已对齐）
| 项 | 决策 |
|---|---|
| 交付形态 | 先 MVP 验证，不纠结最终产品形态 |
| 模型后端 | OpenAI 兼容 API（可切换 DeepSeek / 通义 / 本地 Ollama） |
| 表达训练 | 文本评估进 MVP 后，语音分析（ASR）放后期 |
| 简历脱敏 | 自动标记 + 手动确认打码（可控、误删率低） |
| 向量存储 | 本地 Chroma（文件型，零运维） |
| 元数据存储 | 本地 SQLite |

---

## 2. 用户角色

| 角色 | 说明 | 权限 |
|---|---|---|
| 求职者（主用户） | 使用 Agent 准备面试的本人 | 全部功能 |
| （未来）多租户用户 | SaaS 形态下的多个独立账号 | 数据隔离（本期不实现） |

---

## 3. 总体架构

### 3.1 技术栈（MVP）
- **后端**：Python + FastAPI（RAG / LLM 生态成熟，迭代快）
- **向量库**：Chroma（本地持久化目录，无需独立服务）
- **模型层**：OpenAI 兼容 SDK，配置驱动（`base_url` + `api_key` + `model`），支持热切换
- **元数据库**：SQLite（题目、公司、面试官心态、用户画像等结构化数据）
- **前端**：Vite + React 轻量 Web（先做「知识库管理」「对话」两页，后续扩展）
- **Agent 编排/Harness**：采用显式图编排（参考 LangGraph 的 `StateGraph` + Checkpoint），把面试流程建模为带类型状态的状态机；结构化输出用 `instructor` / `outlines` 在**解码层**强制 JSON Schema，而非仅靠 prompt 约束
- **护栏层（Guardrails）**：参考 OpenAI Agents SDK 思路自研轻量 Guardrail + Tripwire（输入/输出/工具三级校验），用「便宜模型做护栏、贵模型做业务」的职责分离

### 3.2 模块视图
```
                ┌─────────────────────────────────────┐
                │            Web 前端 (React)          │
                └───────┬───────────────┬─────────────┘
                        │               │
            ┌───────────▼───┐     ┌─────▼──────────┐
            │ 知识库/导入页  │     │   对话/训练页   │
            └───────────┬───┘     └─────┬──────────┘
                        │               │
            ┌───────────▼───────────────▼──────────┐
            │            FastAPI 后端服务           │
            │  ┌────────┐ ┌────────┐ ┌──────────┐   │
            │  │导入解析│ │ RAG 检索│ │ Agent 编排│   │
            │  └────────┘ └────────┘ └──────────┘   │
            │  ┌────────┐ ┌────────┐ ┌──────────┐   │
            │  │脱敏模块│ │训练评估│ │ 用户画像 │   │
            │  └────────┘ └────────┘ └──────────┘   │
            └──────┬───────────┬────────────┬───────┘
                   │           │            │
            ┌──────▼───┐ ┌─────▼────┐ ┌────▼──────┐
            │  Chroma  │ │ SQLite   │ │ OpenAI 兼容│
            │ 向量库   │ │ 元数据   │ │  模型 API  │
            └──────────┘ └──────────┘ └───────────┘
```

### 3.3 Agent Harness 设计（核心：保证 I/O 一致、防止漂移）

**Harness 定义**（参考 `awesome-harness-engineering` / LangChain 对 Agent Harness 的解剖）：Harness 是包裹在 LLM 之外的「脚手架」——上下文投递、工具接口、规划产物、验证循环、记忆系统、沙箱。模型本身无法独自可靠完成这些，因此把可控性下沉到 Harness 层，而不是指望 prompt 约束。

本项目的 Harness 由四要素构成（与业界共识一致）：

1. **Agent Loop（代理循环）**：采用 ReAct 式 `思考 → 动作(检索/取画像) → 观察 → 回答` 循环，建模为**显式有向图**（参考 LangGraph：`StateGraph` + 类型化状态 + 条件边 + Checkpoint 持久化），而非自由的多轮对话。
2. **Tool Interface（工具接口）**：`retrieve_knowledge(company, department, mindset)`、`get_user_profile()`、`search_market(target_company)`、（后期）`asr_transcribe()`。每个工具都有严格 JSON Schema，错误以结构化 `tool_result` 返回。
3. **Context Management（上下文管理）**：每轮将「用户画像 + Top-K 检索块 + 目标公司 + 市场环境摘要 + 面试官风格模板」组装进上下文；稳定部分（系统指令、风格模板）走 **Prompt Caching** 降本。
4. **Control Mechanisms（控制机制）**：护栏（输入/输出/工具）、确定性状态机、验证循环——见 3.4。

> 借鉴 `interview-prep-ai`（直接对标的开源面试备战项目）：其核心正是用 **LangChain + Pydantic 强制结构化输出** + **写死在 Agent Loop 中的确定性追问分支**，使模拟面试的节奏与点评格式保持一致。这正是 Harness 而非单纯 prompt 的工程化做法。

### 3.4 防漂移（Anti-Drift）机制

**为什么需要**：LLM 自由生成易「漂移」——同一道题点评格式不统一、追问逻辑随机、越界回答。业界验证的杠杆是「**循环结构 + 约束输出**，而非更大模型」（参考 `statewright` 研究：收窄工具空间后，本地模型 SWE 通过率从 2/10 升至 10/10）。

本项目采用以下组合机制，参考 `interview-prep-ai` 与 OpenAI Agents SDK Guardrails：

1. **结构化输出契约（Structured Output Contract）**
   - 所有 Agent 回复必须遵循 Pydantic Schema，例如一次面试回合：
     ```python
     class InterviewTurn(BaseModel):
         question: str                 # 当前提问
         question_type: Literal["behavioral","technical","pressure","follow_up"]
         references: list[RecordRef]   # 引用的知识库来源（必填，可空数组）
         evaluation: Evaluation | None # 对用户上一轮的评分（首次为空）
         ask_followup: bool            # 是否追问（由确定性规则决定）
         followup_question: str | None
     ```
   - 用 `instructor` / `outlines` 在**解码层**用 JSON Schema/CFG 强制约束，从根上杜绝自由文本漂移，保证前端可稳定解析。

2. **确定性状态机（Deterministic State Machine）**
   - 面试流程建模为状态机：`GREETING → ASK → EVALUATE → {追问 | 下一题} → … → SUMMARY`。
   - 跳题/追问由**评分阈值等确定性规则**驱动（参考 interview-prep-ai：`<50 追问` / `50–75 追问关键细节` / `>75 下一题`），不依赖模型「随意发挥」。

3. **输入护栏（Input Guardrails）**：用户消息先过轻量护栏（规则/便宜模型），校验意图、敏感词、越界请求；触发 `tripwire` 则中断并返回友好提示，**贵模型不启动**（参考 OpenAI Agents SDK 阻塞式 `run_in_parallel=False`）。

4. **输出护栏（Output Guardrails）**：最终回复过大纲校验 + **引用来源必填**校验；不合规则拒绝并重生成。被拒输出**净化不落盘**（参考 SDK 的占位符替换机制），避免污染会话历史。

5. **Prompt 模板化与锁定（Templated & Locked Prompts）**：面试官风格、点评框架、系统指令使用**版本化模板**；关键约束置于「系统指令常驻区」，不受上下文压缩影响（吸取 Claude Code compaction 教训：关键规则不要依赖压缩存活）。

6. **上下文工程（Context Engineering）**：只注入必要上下文，避免无关信息诱发漂移；稳定部分缓存，动态部分（检索结果）每轮刷新。

7. **可观测与回放（Tracing & Replay）**：每次 turn 记录输入/输出/检索/评分/耗时/token，支持回放与回归 eval——把「Harness 调优」变成可度量的迭代（参考 `awesome-harness-engineering` 的 eval harness 思路）。

### 3.5 RAG 检索架构深化

- **MVP（够用即可）**：Chroma 向量检索 + 元数据过滤（`company` / `department` / `mindset` / `question_type`），切片保留 `record_id` 溯源。
- **生产级演进路径**（参考 `trpevski/RAG-in-Production`、`Stages-of-RAG-for-Production`）：
  - **混合检索（Hybrid）**：BM25 关键词 + 语义向量，RRF 融合，兼顾精确词面与语义；
  - **重排序（Rerank）**：cross-encoder reranker 对 Top-N 重排，提升相关度；
  - **分块策略（Chunking）**：按语义边界切分，控制块大小与重叠；
  - **检索评估（Eval）**：引入 ragas 类指标做检索质量回归，防止知识库增长后精度退化。

### 3.6 参考的开源项目架构（架构借鉴）

| 项目 | 借鉴点 |
|---|---|
| **interview-prep-ai**（GitHub） | 直接对标：FastAPI + LangChain + Pydantic 结构化输出 + SSE；RAG 出题语义去重；**确定性追问分支**；Prompt 模板统一面试官风格。可作为 MVP 实现蓝本。 |
| **LangGraph**（langchain-ai） | Agent Loop 建模为带类型状态的有向图 + 条件边 + Checkpoint 持久化；适合实现面试状态机与断点恢复。 |
| **OpenAI Agents SDK（Guardrails）** | 输入/输出/工具三层护栏 + Tripwire 中断 + 模型职责分离（便宜护栏模型 / 贵业务模型）+ 被拒输出净化不落盘。 |
| **awesome-harness-engineering** | Harness 四要素（loop / tool / context / control）与方法论：结构化输出、状态机护栏、验证循环、中间件 hooks、上下文工程、熵管理（防文档漂移）。 |
| **RAG-in-Production / Stages-of-RAG** | 生产级 RAG 范式：混合检索 + 重排序 + 分块 + 评估，作为 MVP 之后的检索增强路线。 |

---

## 4. 功能需求

### 模块一：RAG 知识库（MVP）

**FR-1.1 录入面试记录**
- 用户可手动录入一条面试记录，字段至少包含：
  - 面试问题（必填）
  - 参考答案 / 我的回答（可选）
  - 公司（可选）
  - 部门 / 岗位（可选）
  - 面试官心态标签（如：压力型、温和引导型、技术深挖型、业务导向型，可选多选）
  - 难度、结果（通过/未通过/待定，可选）
  - 备注（可选）

**FR-1.2 自动向量化与切片**
- 录入或导入的文本自动切分为语义块（chunk），生成 embedding 写入 Chroma。
- 切片保留来源 `record_id` 与标签，支持后续精准检索与溯源引用。

**FR-1.3 知识库检索**
- 支持按关键词 / 语义向量检索，过滤条件：公司、部门、心态标签、题型、时间。
- 检索结果展示来源记录与相似度，可追溯到原始录入。

**FR-1.4 编辑与删除**
- 单条记录可编辑、删除；删除时同步清理对应向量。

---

### 模块二：面试题导入（MVP）

**FR-2.1 多来源导入**
- 支持导入方式：纯文本、Markdown 文件、手动粘贴整段。
- 导入时解析为多条面试题（按空行/标题/编号规则切分），批量入库。

**FR-2.2 去重与校验**
- 导入前做简单重复性提示（相同问题 + 相同公司视为疑似重复）。
- 提供「导入预览」让用户确认后再落库。

**FR-2.3 标签批量补全**
- 导入后可对一批记录统一补充公司 / 部门 / 心态标签。

> 后续可扩展：PDF / Word / 网页 URL 导入（非 MVP）。

---

### 模块三：Agent 对话（MVP 核心）

**FR-3.1 用户画像管理**
- 用户维护一份画像：当前技能栈、工作年限、目标岗位、目标公司列表、薄弱环节。
- 画像用于 System Prompt 注入，使提问贴合用户实际。

**FR-3.2 模拟面试官提问**
- Agent 基于以下上下文生成针对性问题：
  1. 知识库召回的相似面试记录（按目标公司/部门/题型加权）
  2. 用户画像（技能、目标）
  3. 当前就业市场环境（用户可手动填写行业趋势摘要，或预留抓取接口）
  4. 对话历史（追问、递进）
- 支持选择「面试官风格」（对应心态标签：压力型 / 温和型 / 深挖型）。

**FR-3.3 作答与点评**
- 用户作答后，Agent 给出结构化点评：
  - 回答覆盖的要点（✅/❌）
  - 结构与时序建议
  - 表达清晰度
  - 引用知识库来源（哪条历史记录相关）
  - 改进建议与示范回答片段

**FR-3.4 流式对话**
- 对话采用 SSE 流式输出，提升交互体验。
- 支持多轮、可重置会话、可切换面试官风格。

**FR-3.5 会话持久化与历史回看（一期补充）**
- 每次对话自动落库：新建会话生成一条 `ChatSession` 记录；每一轮 user / assistant 消息写入 `ChatMessage`（assistant 额外保存结构化 `InterviewTurn`）。
- 提供「会话列表」与「会话历史」接口，前端左侧展示历史会话、点击可加载并继续对话。
- 后端会话状态从数据库按需重建（`InterviewSession.history` 从 `ChatMessage` 恢复并注入后续 LLM 调用），重启后端 / 刷新页面后不丢失上下文。
- 会话标题默认取面试官风格；首条用户回答后自动改为该回答前若干字，便于在列表中辨识会话主题。

---

### 模块四：简历脱敏导入（第二期）

**FR-4.1 简历导入**
- 支持文本 / Markdown / 纯文本粘贴导入简历原文。

**FR-4.2 敏感信息自动标记**
- 自动识别并高亮疑似 PII：姓名、手机号、邮箱、身份证、具体公司名、住址、社交账号。
- 标记以视觉高亮 + 类型标注呈现。

**FR-4.3 手动确认打码**
- 用户对每条高亮标记选择「打码 / 替换为占位符（[姓名]/[电话]） / 忽略」。
- 确认后生成「脱敏版简历」，原文仅本地保留，脱敏版用于后续训练/分析。

**FR-4.4 复用**
- 脱敏版简历可注入用户画像（FR-3.1），使 Agent 更了解用户背景，提问更精准。

---

### 模块五：面试表达训练（文本 MVP 后 / 语音后期）

**FR-5.1 文本作答评估（第三期）**
- 给定一道题（来自知识库或 Agent 出题），用户文本作答。
- Agent 评估：要点完整性、逻辑结构、专业度、STAR 法则运用、可改进点，输出评分（0–100）与雷达图维度。

**FR-5.2 语音作答分析（第四期）**
- 用户用麦克风口语作答，前端采集音频上传。
- 后端 ASR 转写后分析：语速、停顿/卡顿、口头禅（"嗯/那个/其实"）、时长、流畅度评分。
- 与文本评估合并输出「内容 + 表达」双维度报告。

---

## 5. 用例（摘要）

| 用例 ID | 名称 | 主要角色 | 简述 |
|---|---|---|---|
| UC-01 | 录入历史面试 | 求职者 | 手动添加一条带公司/心态标签的面试记录 |
| UC-02 | 批量导入题库 | 求职者 | 粘贴/上传文本，预览后批量入库 |
| UC-03 | 检索知识库 | 求职者 | 按公司+题型检索相似题目与点评 |
| UC-04 | 开始模拟面试 | 求职者 | 选目标公司+风格，Agent 出第一题 |
| UC-05 | 接收点评 | 求职者 | 作答后获得结构化反馈与引用来源 |
| UC-06 | 导入并脱敏简历 | 求职者 | 导入简历→高亮PII→手动确认打码 |
| UC-07 | 文本表达训练 | 求职者 | 作答→评分+改进建议 |
| UC-08 | 语音表达训练 | 求职者 | 口语作答→ASR→流畅度分析 |

---

## 6. 数据模型（核心实体）

### 6.1 InterviewRecord（面试记录）
| 字段 | 类型 | 说明 |
|---|---|---|
| id | UUID | 主键 |
| question | TEXT | 面试问题 |
| my_answer | TEXT | 我的回答（可选） |
| reference_answer | TEXT | 参考答案（可选） |
| company | TEXT | 公司 |
| department | TEXT | 部门/岗位 |
| interviewer_mindset | JSON | 心态标签数组 |
| difficulty | INT | 难度 1–5 |
| result | TEXT | 通过/未通过/待定 |
| note | TEXT | 备注 |
| created_at | DATETIME | 创建时间 |

### 6.2 KnowledgeChunk（向量切片）
| 字段 | 类型 | 说明 |
|---|---|---|
| id | UUID | 主键 |
| record_id | UUID | 来源记录 |
| content | TEXT | 切片文本 |
| embedding | VECTOR | Chroma 管理 |
| tags | JSON | 公司/部门/心态标签 |

### 6.3 UserProfile（用户画像）
| 字段 | 类型 | 说明 |
|---|---|---|
| id | UUID | 主键 |
| skills | TEXT | 技能栈 |
| years | INT | 工作年限 |
| target_role | TEXT | 目标岗位 |
| target_companies | JSON | 目标公司列表 |
| weaknesses | TEXT | 薄弱环节 |
| market_context | TEXT | 就业市场摘要（可选） |
| resume_redacted | TEXT | 脱敏版简历（二期） |

### 6.4 Resume（简历，二期）
| 字段 | 类型 | 说明 |
|---|---|---|
| id | UUID | 主键 |
| raw_text | TEXT | 原文（本地） |
| redacted_text | TEXT | 脱敏版 |
| redactions | JSON | 打码位置与类型数组 |

### 6.5 ChatSession（会话，一期）
| 字段 | 类型 | 说明 |
|---|---|---|
| id | UUID | 主键 |
| title | TEXT | 会话标题（默认风格名，首条回答后更新） |
| interviewer_style | TEXT | 面试官风格（pressure / gentle / deep） |
| target_company | TEXT | 目标公司（可选） |
| target_role | TEXT | 目标岗位（可选） |
| created_at | DATETIME | 创建时间 |
| updated_at | DATETIME | 最近更新时间 |

### 6.6 ChatMessage（会话消息，一期）
| 字段 | 类型 | 说明 |
|---|---|---|
| id | INT | 主键（自增） |
| session_id | UUID | 所属会话（索引） |
| role | TEXT | user / assistant |
| content | TEXT | 消息文本 |
| turn_json | JSON | assistant 的结构化 InterviewTurn（可空） |
| created_at | DATETIME | 创建时间 |

---

## 7. 接口草稿（MVP）

```
# 知识库 / 导入
POST   /api/knowledge/records            # 新增面试记录（触发向量化）
GET    /api/knowledge/records            # 列表/检索（q, company, mindset, page）
GET    /api/knowledge/records/{id}      # 详情
PUT    /api/knowledge/records/{id}      # 编辑
DELETE /api/knowledge/records/{id}      # 删除（同步删向量）
POST   /api/knowledge/import             # 批量导入（预览→确认）

# 用户画像
GET    /api/profile                      # 获取画像
PUT    /api/profile                      # 更新画像

# Agent 对话（SSE 流式）
POST   /api/chat/session                 # 新建会话（指定风格/目标公司）
POST   /api/chat/message                 # 发送消息（stream）
POST   /api/chat/reset                   # 重置会话
GET    /api/chat/sessions                # 会话列表
GET    /api/chat/sessions/{id}/messages  # 会话历史消息

# 简历脱敏（二期）
POST   /api/resume/import                # 导入并标记 PII
POST   /api/resume/redact                # 应用打码

# 表达训练（三期/四期）
POST   /api/training/answer              # 文本评估
POST   /api/training/voice               # 语音评估（音频上传）
```

---

## 8. 非功能需求

- **NFR-1 隐私**：所有数据默认本地存储；模型调用仅传输必要上下文（不传原文简历，除非用户确认）。
- **NFR-2 可配置**：模型 base_url / api_key / model 通过配置文件或环境变量管理，避免硬编码。
- **NFR-3 性能**：单轮对话首字延迟 < 3s（依赖模型）；知识库检索 < 500ms。
- **NFR-4 可观测**：记录每次对话调用的 token 消耗与耗时，便于成本控制。
- **NFR-5 可扩展**：RAG 检索、模型调用、脱敏识别均抽象为接口，便于后续替换实现（如换向量库/本地模型）。
- **NFR-6 可用性**：导入、对话、脱敏均有明确的状态反馈与错误提示。
- **NFR-7 一致性（防漂移）**：所有 Agent 回复必须遵循结构化输出契约（Pydantic Schema），面试流程由确定性状态机驱动；输出需带知识库引用；输入/输出经护栏校验。验收指标：同一目标公司与风格下，连续 10 轮模拟面试的回合结构（提问→点评→决策）100% 可被前端稳定解析，无自由文本格式漂移。
- **NFR-8 可观测**：每次对话 turn 记录输入/输出/检索/评分/耗时/token，支持回放与回归 eval，使 Harness 调优可度量。

---

## 9. 分期里程碑

| 阶段 | 范围 | 关键交付 |
|---|---|---|
| **MVP（一期）** | 模块①②③ | 知识库录入+检索、题库导入、Agent 模拟面试与点评 |
| **二期** | 模块④ | 简历导入 + 自动标记 + 手动脱敏 |
| **三期** | 模块⑤文本 | 文本作答评估 + 评分雷达 |
| **四期** | 模块⑤语音 | 麦克风采集 + ASR + 流畅度分析 |

> MVP 验收标准：用户能录入≥10 条历史面试 → 导入一份题库 → 以目标公司+风格开启模拟面试 → 获得带知识库引用的结构化点评。

---

## 10. 风险与待定项

- **市场环境数据**：MVP 阶段由用户手动填写摘要；后续是否接入实时抓取（如招聘网站趋势）待定。
- **面试官心态标签体系**：需在 MVP 中沉淀一套通用标签词表，避免自由填写导致检索稀疏。
- **语音模块硬件/ASR 依赖**：四期依赖浏览器录音 + ASR 服务（可复用 OpenAI 兼容 Whisper 或本地模型），成本与精度需验证。
- **多用户/云端**：当前为单机本地，SaaS 化需补充账号、多租户隔离、向量库分片（本期不实现）。
- **模型效果**：模拟面试的「针对性」高度依赖知识库质量与画像完整度，需通过 MVP 真实使用验证。

---

## 11. 后续步骤
确认本需求文档后，将进入实现计划（writing-plans）拆分 MVP 的具体任务与开发顺序。
