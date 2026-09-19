# 简历脱敏导入 (Module 4) 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让用户在本地粘贴简历原文，前端自动高亮疑似 PII（姓名/手机号/邮箱/身份证/公司名/住址/社交账号），用户逐条选择「打码 / 占位符 / 忽略」，生成脱敏版并可选存入用户画像，供 Agent 面试时参考背景。

**Architecture:** 后端提供两个纯计算（无状态）接口 `POST /api/resume/detect` 与 `POST /api/resume/mask`，PII 识别用确定性正则（不调用 LLM，零成本、可测试、契合防漂移）。脱敏结果通过 `UserProfile.resume_text` 持久化（原文永不落库，仅脱敏版存）。前端新增 `ResumePage` 完成粘贴→检测→高亮→逐条处置→生成→保存闭环；脱敏版注入 harness 系统提示。

**Tech Stack:** Python + FastAPI + Pydantic + SQLAlchemy(SQLite，异步)；React + TypeScript + react-router-dom + antd（深色 UI）。

**Spec:** `docs/interview-agent-requirements.md` §模块四 FR-4.1 ~ FR-4.4（原定二期，本次提前）。

## Global Constraints

- 原文仅在浏览器本地保留：**任何接口都不得持久化原始简历**，仅 `resume_text`（脱敏版）可入库。
- PII 识别用**确定性正则**，不使用 LLM（避免成本/延迟/非确定性）。公司名与住址为启发式匹配，靠 FR-4.3「忽略」与可编辑脱敏输出兜底。
- 沿用现有分层：`schemas/`(Pydantic) + `services/`(逻辑) + `routers/`(HTTP) + `db/models.py`(ORM)。
- 新增 DB 列必须走 `db/database.py` 的 `_migrate_columns()`（create_all 不给旧表加列），保持幂等。
- 前端已用 antd 深色主题（`ConfigProvider(darkAlgorithm)`），新增弹窗/组件优先 antd；样式变量在 `index.css`（如 `--accent`/`--panel-3`/`--text-dim`）。
- 每个后端纯函数任务必须先写失败测试再实现（TDD），测试放 `backend/tests/`。

---

## Task 1: PII 正则检测服务（后端，纯函数 + TDD）

**Files:**
- Create: `backend/app/services/pii.py`
- Create: `backend/tests/test_pii.py`

**Interfaces:**
- Produces: `detect_pii(text: str) -> list[PiiItem]`、`apply_masks(text: str, selections: list[MaskSelection]) -> tuple[str, list[PiiItem]]`（供 Task 2/3 的 schema 与 router 调用）。
- `PiiItem` / `MaskSelection` 类型在 Task 2 的 `schemas/resume.py` 定义；本任务先用局部 dataclass/typed dict 写实现，Task 2 对齐后替换导入。为避免返工，**本任务直接引用 `app.schemas.resume` 的类型**——因此先以最小形式创建 `schemas/resume.py` 的类型定义（仅 Pydantic 模型，无逻辑），再写本任务。即：先建 `schemas/resume.py`（类型），再写 `pii.py` 与测试。

**步骤（TDD）：**

- [ ] **Step 1: 创建 `schemas/resume.py` 类型**
```python
from pydantic import BaseModel
from typing import Literal

PII_CATEGORIES = ["name", "phone", "email", "id_card", "company", "address", "social"]

class PiiItem(BaseModel):
    category: str          # 见 PII_CATEGORIES
    text: str
    start: int
    end: int

class MaskSelection(BaseModel):
    start: int
    end: int
    category: str
    action: Literal["mask", "placeholder", "ignore"]

class DetectRequest(BaseModel):
    text: str

class DetectResponse(BaseModel):
    items: list[PiiItem]

class MaskRequest(BaseModel):
    text: str
    selections: list[MaskSelection]

class MaskResponse(BaseModel):
    masked_text: str
    applied: list[PiiItem]   # 实际被打码/占位符的项（不含 ignore）
```

- [ ] **Step 2: 写失败测试 `tests/test_pii.py`**
```python
import pytest
from app.services import pii

def test_detect_phone():
    items = pii.detect_pii("我的手机号是13812345678，请联系。")
    phones = [i for i in items if i.category == "phone"]
    assert phones and phones[0].text == "13812345678"

def test_detect_email():
    items = pii.detect_pii("邮箱: jane.doe@example.com 谢谢")
    emails = [i for i in items if i.category == "email"]
    assert emails and "@" in emails[0].text

def test_detect_id_card():
    items = pii.detect_pii("身份证11010519900307123X结尾")
    ids = [i for i in items if i.category == "id_card"]
    assert ids and len(ids[0].text) in (18, 15)

def test_detect_company():
    items = pii.detect_pii("曾就职于字节跳动科技有限公司")
    comp = [i for i in items if i.category == "company"]
    assert comp and "字节" in comp[0].text

def test_detect_address():
    items = pii.detect_pii("住址：北京市海淀区中关村南大街5号")
    addr = [i for i in items if i.category == "address"]
    assert addr

def test_detect_social():
    items = pii.detect_pii("微信: my_wechat_01 联系")
    soc = [i for i in items if i.category == "social"]
    assert soc and "my_wechat_01" in soc[0].text

def test_detect_name_heuristic():
    items = pii.detect_pii("我叫张三，今年28岁")
    names = [i for i in items if i.category == "name"]
    assert names and "张三" in names[0].text

def test_overlap_dedup():
    # 身份证包含连续数字，不应同时被识别为手机号/QQ
    items = pii.detect_pii("身份证11010519900307123X")
    cats = [i.category for i in items]
    assert "phone" not in cats

def test_apply_masks_placeholder():
    text = "手机13812345678联系"
    sels = [{"start": 2, "end": 13, "category": "phone", "action": "placeholder"}]
    out, applied = pii.apply_masks(text, sels)
    assert "[电话]" in out and "13812345678" not in out
    assert len(applied) == 1

def test_apply_masks_mask():
    text = "手机13812345678联系"
    sels = [{"start": 2, "end": 13, "category": "phone", "action": "mask"}]
    out, _ = pii.apply_masks(text, sels)
    assert "█" in out and "13812345678" not in out

def test_apply_masks_ignore():
    text = "手机13812345678联系"
    sels = [{"start": 2, "end": 13, "category": "phone", "action": "ignore"}]
    out, applied = pii.apply_masks(text, sels)
    assert "13812345678" in out and applied == []
```

- [ ] **Step 3: 运行测试确认失败**
Run: `cd backend && python -m pytest tests/test_pii.py -v`
Expected: FAIL（`ModuleNotFoundError: app.services.pii` 或属性缺失）

- [ ] **Step 4: 实现 `services/pii.py`**
```python
import re
from app.schemas.resume import PiiItem, MaskSelection

_PLACEHOLDER = {
    "name": "[姓名]", "phone": "[电话]", "email": "[邮箱]",
    "id_card": "[身份证]", "company": "[公司]", "address": "[住址]",
    "social": "[社交账号]",
}

_PATTERNS = {
    "phone": re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"),
    "email": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    "id_card": re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)"),
    "company": re.compile(r"[一-龥A-Za-z0-9]+?(?:公司|集团|科技|有限公司|股份公司|企业|银行|大学|学院|研究所|医院|工厂)"),
    "address": re.compile(r"[一-龥]{2,}(?:省|市|区|县|镇|路|街|道|号|栋|幢|单元|室|楼|大厦|广场|园区|巷)"),
    "social": re.compile(r"(?:微信|微信号|WeChat|QQ|qq|抖音|小红书|微博)[：:\s]*[A-Za-z0-9_-]{4,}"),
    "name": re.compile(r"(?:姓名|我叫|名字)[：:\s]*([一-龥]{2,4})|([一-龥]{2,3})(?:先生|女士|同学)"),
}

def detect_pii(text: str) -> list[PiiItem]:
    raw: list[PiiItem] = []
    for cat, pat in _PATTERNS.items():
        for m in pat.finditer(text):
            # name 用捕获组，取实际姓名片段
            if cat == "name":
                val = m.group(1) or m.group(2)
                if not val:
                    continue
                start, end = m.span(1) if m.group(1) else m.span(2)
            else:
                val = m.group(0)
                start, end = m.span(0)
            raw.append(PiiItem(category=cat, text=val, start=start, end=end))
    # 去重叠：按长度降序、起点升序，接受不重叠的（长匹配优先，避免身份证被手机号/QQ切碎）
    raw.sort(key=lambda x: (-(x.end - x.start), x.start))
    accepted: list[PiiItem] = []
    for it in raw:
        if any(not (it.end <= a.start or it.start >= a.end) for a in accepted):
            continue
        accepted.append(it)
    accepted.sort(key=lambda x: x.start)
    return accepted

def apply_masks(text: str, selections: list[MaskSelection]) -> tuple[str, list[PiiItem]]:
    applied: list[PiiItem] = []
    # 从右往左替换，避免索引位移；仅非 ignore 的项生效
    ops = sorted(
        [s for s in selections if s.action != "ignore"],
        key=lambda s: s.start, reverse=True,
    )
    out = text
    for s in ops:
        if s.start < 0 or s.end > len(out) or s.start >= s.end:
            continue
        if s.action == "placeholder":
            repl = _PLACEHOLDER.get(s.category, "[PII]")
        else:  # mask
            repl = "█" * max(len(out[s.start:s.end]), 3)
        out = out[:s.start] + repl + out[s.end:]
        applied.append(PiiItem(category=s.category, text=out[s.start:s.start+len(repl)], start=s.start, end=s.start+len(repl)))
    applied.sort(key=lambda x: x.start)
    return out, applied
```

- [ ] **Step 5: 运行测试确认通过**
Run: `cd backend && python -m pytest tests/test_pii.py -v`
Expected: 全部 PASS

- [ ] **Step 6: 提交**
```bash
git add backend/app/schemas/resume.py backend/app/services/pii.py backend/tests/test_pii.py
git commit -m "feat(resume): 确定性正则 PII 检测与打码服务 + 测试"
```

---

## Task 2: 简历接口 Router 与 main 装配

**Files:**
- Create: `backend/app/routers/resume.py`
- Modify: `backend/app/main.py`（include router）

**Interfaces:**
- Consumes: `detect_pii` / `apply_masks`（Task 1）；`DetectRequest`/`DetectResponse`/`MaskRequest`/`MaskResponse`（Task 1 schema）。
- Produces: HTTP 端点 `POST /api/resume/detect`、`POST /api/resume/mask`。

- [ ] **Step 1: 创建 `routers/resume.py`**
```python
from fastapi import APIRouter
from app.schemas.resume import DetectRequest, DetectResponse, MaskRequest, MaskResponse
from app.services import pii

router = APIRouter(prefix="/api/resume", tags=["resume"])

@router.post("/detect", response_model=DetectResponse)
async def detect(req: DetectRequest):
    return DetectResponse(items=pii.detect_pii(req.text))

@router.post("/mask", response_model=MaskResponse)
async def mask(req: MaskRequest):
    masked_text, applied = pii.apply_masks(req.text, req.selections)
    return MaskResponse(masked_text=masked_text, applied=applied)
```

- [ ] **Step 2: 在 `main.py` 装配**
在现有 `from app.routers import knowledge, profile, chat` 改为
`from app.routers import knowledge, profile, chat, resume`，
并在 `app.include_router(chat.router)` 后增加 `app.include_router(resume.router)`。

- [ ] **Step 3: 冒烟验证**
Run: `cd backend && python -c "from app.main import app; print([r.path for r in app.routes if 'resume' in r.path])"`
Expected: 输出含 `/api/resume/detect` 与 `/api/resume/mask`

- [ ] **Step 4: 提交**
```bash
git add backend/app/routers/resume.py backend/app/main.py
git commit -m "feat(resume): 简历检测/打码 HTTP 接口"
```

---

## Task 3: 画像持久化脱敏版简历（resume_text）

**Files:**
- Modify: `backend/app/schemas/profile.py`
- Modify: `backend/app/db/models.py`（`UserProfileRow` 加列）
- Modify: `backend/app/db/database.py`（`_MISSING_COLUMNS` 加 `user_profile`）
- Modify: `backend/app/services/profile_service.py`（读写 `resume_text`）

**Interfaces:**
- Consumes: 现有 `UserProfile` 单一行（id=1）模式。
- Produces: `UserProfile.resume_text: str`（供 Task 4 harness 与前端 `updateProfile` 使用）。

- [ ] **Step 1: schema 加字段**
`profile.py` 的 `UserProfile` 增加 `resume_text: str = ""`（置于 `market_context` 之后）。

- [ ] **Step 2: model 加列**
`models.py` 的 `UserProfileRow` 在 `market_context` 行后加
`resume_text: Mapped[str | None] = mapped_column(Text, nullable=True)`。
注意 import 区已有 `Text`。

- [ ] **Step 3: 迁移登记**
`database.py` 的 `_MISSING_COLUMNS` 字典增加：
`"user_profile": [("resume_text", "TEXT")]`。

- [ ] **Step 4: service 读写**
`profile_service.py` 的 `get_profile` 与 `update_profile` 两处 `UserProfile(...)` 构造增加 `resume_text=row.resume_text or ""`；`update_profile` 写入 `row.resume_text = data.resume_text`。

- [ ] **Step 5: 编译校验**
Run: `cd backend && python -m py_compile app/schemas/profile.py app/db/models.py app/db/database.py app/services/profile_service.py && echo OK`
Expected: OK

- [ ] **Step 6: 提交**
```bash
git add backend/app/schemas/profile.py backend/app/db/models.py backend/app/db/database.py backend/app/services/profile_service.py
git commit -m "feat(profile): 新增 resume_text 持久化脱敏版简历"
```

---

## Task 4: 脱敏版简历注入面试系统提示（FR-4.4）

**Files:**
- Modify: `backend/app/services/interview_harness.py`（`_system()` 的 ctx）

**Interfaces:**
- Consumes: `self.profile.resume_text`（Task 3 新增）。
- Produces: 系统提示包含候选人背景（脱敏简历要点）。

- [ ] **Step 1: 在 `_system()` 的 ctx 末尾追加**
在现有 `ctx = (...)` 拼接之后、`if json_mode:` 之前，增加：
```python
if p.resume_text:
    snippet = p.resume_text[:1500]
    ctx += f"\n候选人脱敏简历（已打码，用于了解其背景，提问可据此关联经历）：{snippet}"
```
（`p` 为 `self.profile`，在该方法开头已定义。）

- [ ] **Step 2: 编译校验**
Run: `cd backend && python -m py_compile app/services/interview_harness.py && echo OK`
Expected: OK

- [ ] **Step 3: 提交**
```bash
git add backend/app/services/interview_harness.py
git commit -m "feat(harness): 将脱敏简历注入系统提示，丰富面试官背景"
```

---

## Task 5: 前端类型与 API（types.ts / api.ts）

**Files:**
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/api.ts`

**Interfaces:**
- Produces: 前端类型 `PiiItem`/`DetectRequest`/`DetectResponse`/`MaskRequest`/`MaskResponse`；API 方法 `detectPII`/`maskResume`；`UserProfile` 增加 `resume_text`。

- [ ] **Step 1: types.ts 增加类型**
在 `UserProfile` 增加 `resume_text?: string | null`（置于 `market_context` 之后）。
在文件末尾新增：
```ts
export type PiiCategory = 'name' | 'phone' | 'email' | 'id_card' | 'company' | 'address' | 'social'
export interface PiiItem { category: PiiCategory; text: string; start: number; end: number }
export interface MaskSelection { start: number; end: number; category: PiiCategory; action: 'mask' | 'placeholder' | 'ignore' }
export interface DetectResponse { items: PiiItem[] }
export interface MaskResponse { masked_text: string; applied: PiiItem[] }
```

- [ ] **Step 2: api.ts 增加方法**
在 `api` 对象中增加：
```ts
detectPII(text: string) {
  return fetch(`${BASE}/api/resume/detect`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
  }).then((r) => json<DetectResponse>(r))
},
maskResume(text: string, selections: MaskSelection[]) {
  return fetch(`${BASE}/api/resume/mask`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, selections }),
  }).then((r) => json<MaskResponse>(r))
},
```
（`updateProfile` 已存在，无需新增。）

- [ ] **Step 3: 前端类型检查**
确认编辑器/LSP 无报错（0 diagnostics）。如有 `tsc`，可运行 `cd frontend && npx tsc --noEmit`。

- [ ] **Step 4: 提交**
```bash
git add frontend/src/types.ts frontend/src/api.ts
git commit -m "feat(resume): 前端类型与 detect/mask API"
```

---

## Task 6: 简历脱敏页面 ResumePage

**Files:**
- Create: `frontend/src/pages/ResumePage.tsx`

**Interfaces:**
- Consumes: `api.detectPII` / `api.maskResume` / `api.getProfile` / `api.updateProfile`（Task 5）。
- Produces: 完整的粘贴→检测→高亮→逐条处置→生成→保存 UI。

**UI 行为：**
- 顶部一个 `Input.TextArea` 粘贴原文（`original` state）。
- 「自动检测」按钮 → `detectPII(original)` → 存入 `items: PiiItem[]`，每项默认 `action: 'placeholder'`。
- 渲染高亮预览：把 `original` 按 `items`（已按 start 排序、无重叠）切片，PII 片段包 `<span class="pii-hl" data-cat={cat}>` 并显示类型角标。
- 每个检测项一行：类型标签 + 命中文本 + 三个 `Radio`（`打码`/`占位符`/`忽略`，默认占位符），改变即更新 `selections` 并实时刷新预览。
- 「生成脱敏版」按钮 → `maskResume(original, selections)` → 把返回的 `masked_text` 放进可编辑 `Input.TextArea`（`masked` state），允许用户手动微调（弥补公司/住址漏检）。
- 「保存到画像」按钮 → `getProfile()` 合并 `resume_text: masked` 后 `updateProfile(...)`，成功提示。

- [ ] **Step 1: 创建 `ResumePage.tsx`**
```tsx
import { useEffect, useMemo, useState } from 'react'
import { App as AntApp, Button, Input, Radio, Tag } from 'antd'
import { api } from '../api'
import type { PiiItem, PiiCategory, MaskSelection, UserProfile } from '../types'

const CAT_LABEL: Record<PiiCategory, string> = {
  name: '姓名', phone: '手机号', email: '邮箱', id_card: '身份证',
  company: '公司', address: '住址', social: '社交账号',
}

export default function ResumePage() {
  const { message } = AntApp.useApp()
  const [original, setOriginal] = useState('')
  const [items, setItems] = useState<PiiItem[]>([])
  const [actions, setActions] = useState<Record<number, MaskSelection['action']>>({})
  const [masked, setMasked] = useState('')
  const [busy, setBusy] = useState(false)

  const selections = useMemo<MaskSelection[]>(
    () => items.map((it, i) => ({
      start: it.start, end: it.end, category: it.category,
      action: actions[i] ?? 'placeholder',
    })),
    [items, actions],
  )

  async function detect() {
    if (!original.trim()) { message.warning('请先粘贴简历原文'); return }
    setBusy(true); setMasked('')
    try {
      const r = await api.detectPII(original)
      setItems(r.items)
      message.success(`检测到 ${r.items.length} 处疑似敏感信息`)
    } catch (e) { message.error((e as Error).message) } finally { setBusy(false) }
  }

  async function generate() {
    setBusy(true)
    try {
      const r = await api.maskResume(original, selections)
      setMasked(r.masked_text)
      message.success('已生成脱敏版，可手动微调后保存')
    } catch (e) { message.error((e as Error).message) } finally { setBusy(false) }
  }

  async function save() {
    if (!masked.trim()) { message.warning('请先生成脱敏版'); return }
    try {
      const p: UserProfile = await api.getProfile()
      await api.updateProfile({ ...p, resume_text: masked })
      message.success('已保存到画像，面试 Agent 将参考该背景')
    } catch (e) { message.error((e as Error).message) }
  }

  // 高亮预览：按 items 切片 original
  const segments = useMemo(() => {
    if (!items.length) return [{ text: original, pii: null as PiiItem | null }]
    const segs: { text: string; pii: PiiItem | null }[] = []
    let cursor = 0
    for (const it of items) {
      if (it.start > cursor) segs.push({ text: original.slice(cursor, it.start), pii: null })
      segs.push({ text: original.slice(it.start, it.end), pii: it })
      cursor = it.end
    }
    if (cursor < original.length) segs.push({ text: original.slice(cursor), pii: null })
    return segs
  }, [original, items])

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <div className="kicker">Resume Desensitization</div>
          <h2>简历脱敏导入</h2>
        </div>
      </div>

      <section className="card">
        <label className="block-label">① 粘贴简历原文（仅本地处理，不会上传原文）</label>
        <Input.TextArea rows={8} value={original} onChange={(e) => setOriginal(e.target.value)}
          placeholder="支持文本 / Markdown / 纯文本。粘贴后点击「自动检测」。" />
        <div className="actions">
          <Button type="primary" onClick={detect} loading={busy} disabled={!original.trim()}>自动检测</Button>
        </div>
      </section>

      {items.length > 0 && (
        <section className="card">
          <label className="block-label">② 检测预览（高亮为疑似 PII，逐条选择处置方式）</label>
          <div className="resume-preview">
            {segments.map((s, i) => s.pii ? (
              <span key={i} className="pii-hl" data-cat={s.pii.category}>
                {s.text}<sup>{CAT_LABEL[s.pii.category]}</sup>
              </span>
            ) : <span key={i}>{s.text}</span>)}
          </div>
          <div className="pii-list">
            {items.map((it, i) => (
              <div key={i} className="pii-row">
                <Tag color="warning">{CAT_LABEL[it.category]}</Tag>
                <code className="pii-text">{it.text}</code>
                <Radio.Group
                  size="small"
                  value={actions[i] ?? 'placeholder'}
                  onChange={(e) => setActions((a) => ({ ...a, [i]: e.target.value }))}
                  optionType="button"
                  options={[
                    { label: '占位符', value: 'placeholder' },
                    { label: '打码', value: 'mask' },
                    { label: '忽略', value: 'ignore' },
                  ]}
                />
              </div>
            ))}
          </div>
          <div className="actions">
            <Button type="primary" onClick={generate} loading={busy}>生成脱敏版</Button>
          </div>
        </section>
      )}

      {masked && (
        <section className="card">
          <label className="block-label">③ 脱敏版（可手动微调，弥补漏检）</label>
          <Input.TextArea rows={8} value={masked} onChange={(e) => setMasked(e.target.value)} />
          <div className="actions">
            <Button type="primary" onClick={save}>保存到画像</Button>
          </div>
        </section>
      )}
    </div>
  )
}
```

- [ ] **Step 2: 前端类型检查**
确认 LSP 0 报错（antd 的 `Radio`/`Tag` 来自已安装依赖；若未安装则先 `npm i antd` 已在项目内，无需新增）。

- [ ] **Step 3: 提交**
```bash
git add frontend/src/pages/ResumePage.tsx
git commit -m "feat(resume): 简历脱敏页面（检测/高亮/逐条处置/生成/保存）"
```

---

## Task 7: 路由与导航接入 + 样式

**Files:**
- Modify: `frontend/src/App.tsx`（新增 tab 与 route）
- Modify: `frontend/src/index.css`（新增 `.resume-preview` / `.pii-hl` / `.pii-list` / `.pii-row` / `.block-label` 等）

**Interfaces:**
- Consumes: `ResumePage`（Task 6）。

- [ ] **Step 1: App.tsx 加路由**
`import ResumePage from './pages/ResumePage'`；
`tabs` 数组追加 `{ to: '/resume', label: 'Resume' }`；
`Routes` 内追加 `<Route path="/resume" element={<ResumePage />} />`。

- [ ] **Step 2: index.css 加样式**
在文件末尾追加（用项目已有变量 `--accent`/`--panel-3`/`--text-dim`/`--border`）：
```css
.block-label { display:block; font-size:13px; font-weight:600; color:var(--text-dim); margin-bottom:8px; }
.resume-preview {
  background: var(--panel-3); border:1px solid var(--border); border-radius:12px;
  padding:14px 16px; font-size:14px; line-height:1.9; white-space:pre-wrap; word-break:break-word;
}
.pii-hl { background: rgba(255,180,60,.18); border-bottom:2px solid #ffb43c; border-radius:3px; padding:0 2px; }
.pii-hl sup { font-size:9px; color:#ffb43c; margin-left:2px; }
.pii-list { margin-top:14px; display:flex; flex-direction:column; gap:8px; }
.pii-row { display:flex; align-items:center; gap:10px; flex-wrap:wrap; }
.pii-text { background:var(--panel-3); padding:2px 6px; border-radius:6px; font-size:12.5px; }
.actions { margin-top:14px; display:flex; gap:10px; }
```

- [ ] **Step 3: 前端构建/类型检查**
如需：`cd frontend && npx tsc --noEmit`。确认无错。

- [ ] **Step 4: 提交**
```bash
git add frontend/src/App.tsx frontend/src/index.css
git commit -m "feat(resume): 接入导航路由与脱敏页样式"
```

---

## Self-Review

**1. Spec 覆盖（FR-4.1 ~ FR-4.4）：**
- FR-4.1 文本/Markdown/纯文本粘贴导入 → Task 6 的 `Input.TextArea`（不区分格式，原样处理）。✅
- FR-4.2 自动识别并高亮 7 类 PII + 类型标注 → Task 1 正则 + Task 6 高亮 `<sup>` 角标。✅（公司/住址为启发式，已在约束中说明）
- FR-4.3 逐条手动确认「打码/占位符/忽略」→ Task 6 `Radio.Group` + Task 1 `apply_masks`。✅
- FR-4.4 脱敏版注入画像 → Task 3 `resume_text` 持久化 + Task 4 harness 注入 + Task 6「保存到画像」。✅

**2. Placeholder 扫描：** 无 TBD/TODO；每个代码步骤均给出可运行片段。

**3. 类型一致性：** `PiiItem`/`MaskSelection` 在 Task 1 schema 定义，Task 2 router、Task 5 前端类型、Task 6 均复用同名同字段；`resume_text` 在 Task 3 schema/model/service 与 Task 4/5/6 一致。`action` 取值 `mask|placeholder|ignore` 在 schema、apply_masks、前端 Radio 三处一致。✅

**已知限制（写入说明，非本次范围）：** 公司名/住址为启发式正则，可能漏检或误检；靠「忽略」与可编辑脱敏输出兜底。未实现「手动框选新增标记」（MVP 不做，YAGNI）。原文仅在浏览器内存中，刷新即丢失（不持久化），符合 FR「原文仅本地保留」。
