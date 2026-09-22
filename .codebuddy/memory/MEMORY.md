# 长期记忆 (MEMORY.md)

## 项目：speak-agent（面试能力提升 Agent）
- 目标：AI 面试教练，闭环 = 沉淀(RAG知识库) → 导入(面试题) → 对话(Agent模拟面试) → 脱敏(简历) → 训练(表达)。
- 形态：先 MVP 验证，不纠结最终产品形态（非 SaaS，单机本地优先）。
- 模型后端：OpenAI 兼容 API（配置驱动 base_url/api_key/model，可切 DeepSeek/通义/本地 Ollama）。
- 技术栈建议：Python + FastAPI + Chroma(本地向量) + SQLite(元数据) + Vite/React 前端。
- 分期：MVP=模块①②③(知识库+RAG+导入+对话)；二期=④简历脱敏(自动标记+手动确认打码)；三期=⑤文本表达训练；四期=⑤语音ASR分析。
- 简历脱敏决策：自动标记 + 手动确认打码（可控、误删率低）。
- 表达训练：文本评估进 MVP 后，语音(ASR)放后期。
- 需求文档位置：docs/interview-agent-requirements.md（v1.0, 2026-09-16；已补充技术深度；原中文名已重命名为英文名）。

## 技术架构关键决策（防漂移 / Harness）
- 采用 Agent Harness 工程保证 I/O 一致、防止回复漂移（用户明确要求参考 GitHub 优秀开源架构）。
- Harness 四要素：Agent Loop(ReAct/显式图) + Tool Interface + Context Management + Control Mechanisms。
- 防漂移机制（已写入需求文档 §3.3-3.4）：①结构化输出契约(Pydantic Schema + instructor/outlines 解码层强制) ②确定性状态机驱动面试流程(追问/跳题由评分阈值确定性规则) ③输入/输出/工具三层 Guardrail + Tripwire(参考 OpenAI Agents SDK，便宜模型做护栏/贵模型做业务) ④Prompt 模板化与锁定 ⑤上下文工程(Prompt Caching) ⑥可观测回放(eval harness)。
- 参考的开源项目：interview-prep-ai(直接对标, FastAPI+LangChain+Pydantic+SSE+确定性追问)、LangGraph(StateGraph+Checkpoint)、OpenAI Agents SDK Guardrails、awesome-harness-engineering、RAG-in-Production/Stages-of-RAG(混合检索+重排序+评估)。
- RAG：MVP 用 Chroma 向量+元数据过滤；演进路径=混合检索(BM25+向量+RRF)+rerank+评估(ragas)。

## 对话历史持久化（已实现，2026-09-18）
- **背景**：原 Agent 对话历史未持久化（纯内存态 `SESSIONS` + `InterviewSession.history`），刷新/重启/新建会话后丢失，无历史列表。
- **文档**：已补 FR-3.5「会话持久化与历史回看」；§6 增加 `ChatSession`/`ChatMessage` 表；§7 增加 `GET /api/chat/sessions`、`GET /api/chat/sessions/{id}/messages`。
- **实现**：
  - 后端 `db/models.py` 新增 `ChatSession`+`ChatMessage`；`services/chat_service.py` 负责 CRUD；`routers/chat.py` 改为落库 + 列表/历史接口 + `_get_or_load_session` 从 DB 重建会话（恢复 history 与 questions_asked）。
  - `services/llm.py` 的 `chat_structured`/`stream_text` 增加 `history` 参数；`interview_harness.py` 将 `self.history` 注入所有 LLM 调用，使多轮/续聊有上下文。
  - 前端 `ChatPage.tsx` 改为两栏（侧栏会话列表 + 主对话区），支持新建/点击历史回看续聊/重命名/删除；`api.ts`/`types.ts` 增加 `listSessions`/`getSessionMessages`/`renameSession`/`deleteSession` 与类型；`index.css` 增加侧栏布局与 hover 操作按钮。后端额外 `PATCH /api/chat/sessions/{id}`（重命名）、`DELETE /api/chat/sessions/{id}`（删除会话及全部消息，并清理内存缓存）。
- 注意：会话状态机 `state` 重建时默认 ASKING（未持久化 SUMMARY 终态），续聊已结束会话会当作新一轮继续——MVP 可接受。

## 前端技术栈与 UI 约定（2026-09-18）
- 已引入 `antd`（v5）+ `@ant-design/icons`，并在 `main.tsx` 用 `ConfigProvider(theme.darkAlgorithm)` + `App` 包裹（项目为深色 UI，变量在 `index.css`）—— antd 组件必须配深色算法。
- 弹窗/确认/轻提示优先用 antd：`Modal`+`Input` 做重命名输入、`Popconfirm` 做删除气泡确认、`message` 经 `App.useApp()` 获取（勿用静态 `message`，否则缺 context 警告）。
- 会话列表项的重命名/删除即采用上述 antd 组件（见 `frontend/src/pages/ChatPage.tsx`）。

## 题库导入功能设计决策（2026-09-17，已批准实现）
- **方向**：用户粘贴任意杂乱文本/Markdown，AI 负责拆题、纠偏、整理答案；不要求用户手写固定 Markdown 格式。
- **AI 抽取范围**：只抽内容字段（question / my_answer / reference_answer / note），不猜元数据。
- **元数据交互**：弹窗设全局默认值（company/department/mindset/difficulty/result）应用到全部题目；预览表格里每条可单独覆盖。心态标签固定词表：压力型/温和引导型/技术深挖型/业务导向型。
- **去重**：预览时按 normalize(question)+company 比对现有记录，疑似重复标⚠️且默认不勾选。
- **实现**：后端 `POST /api/knowledge/parse`（复用 `llm.chat_structured` + `ParsedQuestionBank` Schema，清洗丢弃空题、限 30 条）；前端 `KnowledgePage.tsx` 的「AI 智能导入」卡片 + 弹窗 + 预览表格；保留「快速文本导入」纯文本兜底。心态词表 `MINDSET_OPTIONS` 在 KnowledgePage.tsx 与需求 FR-10 呼应。

## 评分校准分层原则（关键，2026-09-22，已校正为"一致性/防漂移"表述）
- **核心规则**：LLM 只负责产出"原始分"（唯一不可再生的字段）；`adaptation.calibrate_score` / `score_to_level` / `next_difficulty` 全是**确定性纯函数**，属于"视图/派生"，绝不能当作"存进数据库的事实"。
- **校准层的本职 = 一致性 / 防漂移，NOT 准确性**：它把 LLM 原始分单调重定标到统一的难度区间，消除跨模型/提示词/时间的系统性刻度漂移，使分数可比、稳定、改自己代码不飘。**它不修正 LLM 原始分的排序误差与噪声**（单调映射原样继承）——绝对准确度需靠更好的 rubric / 参考锚定 / 人工标注（见 eval 设计）。`adaptation.py` 注释已据此改写，勿再写成"锚定现实/更准"。
- **存储约定**（`interview_harness.py`）：trace 的 `raw_llm_output` 字段必须在**校准前**冻结原始 LLM 输出（raw 分），`score`/`level`/`interview_turn` 列才存校准后结果。已修复：原先第 193 行原地覆盖 `evaluation.score` 后，第 264 行又把已校准的 `eval_turn` 序列化进 `raw_llm_output`，导致 raw 丢失。
- **含义**：改 `adaptation.py`（校准规则/难度档/等级阈值）后，历史对话分数会过时，但**重算零 token**——只需对所有 trace 的 `raw_llm_output` 重跑 `calibrate_score(raw, diff)` 即可。若 raw 被丢弃则必须重烧 LLM，这是设计红线。
- **反向风险**：过度重定标（0.6 拉向中心 + clamp）可能把 LLM 能区分的高低分都压平到同一档，损失区分度；调 `SCORE_BAND` 区间宽度是权衡（太宽→一致性差，太窄→压平）。
- eval replay（`backend/scripts/replay.py` + `backend/tests/test_eval_replay.py`）的 fake 模式即利用此分层：替换 LLM 为确定性替身只注入 raw，下游全跑真实校准逻辑做回归网关（CI 不烧 token）；`--mode live` 才跑真模型验点评质量（监控 LLM raw 漂移/退化这一层残留误差）。
