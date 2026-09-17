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

## 题库导入功能设计决策（2026-09-17，已批准实现）
- **方向**：用户粘贴任意杂乱文本/Markdown，AI 负责拆题、纠偏、整理答案；不要求用户手写固定 Markdown 格式。
- **AI 抽取范围**：只抽内容字段（question / my_answer / reference_answer / note），不猜元数据。
- **元数据交互**：弹窗设全局默认值（company/department/mindset/difficulty/result）应用到全部题目；预览表格里每条可单独覆盖。心态标签固定词表：压力型/温和引导型/技术深挖型/业务导向型。
- **去重**：预览时按 normalize(question)+company 比对现有记录，疑似重复标⚠️且默认不勾选。
- **实现**：后端 `POST /api/knowledge/parse`（复用 `llm.chat_structured` + `ParsedQuestionBank` Schema，清洗丢弃空题、限 30 条）；前端 `KnowledgePage.tsx` 的「AI 智能导入」卡片 + 弹窗 + 预览表格；保留「快速文本导入」纯文本兜底。心态词表 `MINDSET_OPTIONS` 在 KnowledgePage.tsx 与需求 FR-10 呼应。
