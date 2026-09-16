# 面试训练 Agent — MVP 后端

基于 FastAPI 的面试教练后端：知识库录入 + 向量化检索（RAG）、用户画像、以及由
**确定性状态机 + 结构化输出 + 护栏（Guardrail + Tripwire）**驱动的模拟面试 Agent 对话。

## 架构要点（防漂移）
- **Harness 四要素**：Agent Loop（ReAct/状态机）+ Tool Interface + Context Management + Control Mechanisms。
- **结构化输出契约**：所有 Agent 回复遵循 `InterviewTurn` Pydantic Schema，`instructor` 在解码层强制约束，杜绝自由文本漂移。
- **确定性状态机**：`ASKING → EVALUATING → SUMMARY`，追问/跳题由评分阈值等确定性规则驱动。
- **护栏 + Tripwire**：`input_guardrail` / `output_guardrail`，输入空/注入即中断，输出评分越界即拒。

## 启动

```bash
# 1. 进入后端目录（必须在 backend/ 下，否则找不到 app 包与 .env）
cd backend

# 2. 创建并激活虚拟环境（可选但推荐）
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Linux/macOS

# 3. 安装依赖
pip install -r requirements.txt

# 4. 准备环境变量
cp .env.example .env
#   然后编辑 .env，至少填入：
#     LLM_API_KEY=sk-...        # DeepSeek 密钥（对话 / 点评用）
#     EMBED_API_KEY=sk-...      # OpenAI 密钥（知识库向量化用；DeepSeek 不提供 embedding）
#     CHAT_MODEL=deepseek-flash # DeepSeek 模型 ID（v4flash 不是合法 ID）

# 5. 启动（务必用 python -m uvicorn；裸 uvicorn 可能不在 PATH）
python -m uvicorn app.main:app --reload --port 8000

# 6. 验证
curl http://127.0.0.1:8000/health     # 期望 {"status":"ok"}
```

> 知识库「新增记录」依赖 Embedding，若 `EMBED_API_KEY` 为空会报错；对话与点评只依赖 `LLM_API_KEY`（DeepSeek）。
> 修改 `.env` 后需重启 uvicorn（`--reload` 仅监听 `.py`，不重载 `.env`）。

## 接口速览
- `POST /api/knowledge/records`        录入面试记录（自动向量化）
- `GET  /api/knowledge/records`        检索（company / mindset 过滤）
- `DELETE /api/knowledge/records/{id}` 删除（同步清理向量）
- `POST /api/knowledge/import`         批量导入
- `GET  /api/profile`  | `PUT /api/profile`   用户画像
- `POST /api/chat/session`             开启模拟面试（返回首题）
- `POST /api/chat/message`             SSE 流式作答（`data:` token 流 + 末事件 `event: turn` 含完整 `InterviewTurn` JSON）

## 测试
```bash
pip install -r requirements.txt
pytest                       # 全部离线可跑（LLM/embedding 已 mock）
```

## 目录
```
app/
  config.py           配置（pydantic-settings，读 .env）
  main.py             FastAPI 入口
  db/                SQLAlchemy 模型 + 会话
  schemas/           Pydantic 契约（InterviewTurn 等）
  rag/               embedder / chunker / Chroma store
  services/          llm / guardrails / knowledge / profile / interview_harness
  routers/           knowledge / profile / chat(SSE)
tests/               单元测试 + 集成测试（mock LLM 与向量检索）
```
