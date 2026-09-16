# Speak Agent — 前端

React + TypeScript（Vite）单页应用，对接 `backend/` 的 FastAPI 接口。

## 页面
- **Coach**：选择教练风格 + 目标公司，开启 SSE 流式对话；逐字展示提问，完成后展示结构化点评（评分 / 覆盖要点 / 遗漏要点 / 建议）与引用来源。
- **Knowledge**：新增记录、批量导入（空行分隔）、按公司筛选、删除。
- **Profile**：维护技能 / 年限 / 目标岗位 / 目标公司 / 薄弱点 / 市场环境，注入到对话的 System Prompt。

## 开发
```bash
cd frontend
npm install
npm run dev        # http://localhost:5173，/api 已代理到 http://localhost:8000
```
确保后端已启动：`cd ../backend && uvicorn app.main:app --reload`

## 构建
```bash
npm run build      # tsc 类型检查 + vite 打包到 dist/
npm run preview
```

## 接口约定
- 基础路径读取 `VITE_API_BASE`（默认空，走 Vite 代理）。
- 流式消息（`POST /api/chat/message`）为 SSE：`data: {"type":"token","text":...}` 逐段，末尾 `event: turn` + `data: <InterviewTurn JSON>`。
- 类型定义见 `src/types.ts`，与后端 Pydantic Schema 对应。
