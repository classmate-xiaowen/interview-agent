"""零成本重算历史面试评分（改 adaptation.py 后无需重烧 LLM）。

原理：trace 的 `raw_llm_output` 存的是校准前的"模型原始分"，`difficulty` 存评该轮时的难度档。
校准 `calibrate_score` / `score_to_level` 是确定性纯函数，因此改了评分框架后，只需对历史
turn_traces 重跑这两个函数即可刷新 score/level/interview_turn —— 全程不调用 LLM，0 token。

用法：
  python -m scripts.backfill_scores            # 实际写入全部需要更新的行
  python -m scripts.backfill_scores --dry-run  # 只统计，不写库
  python -m scripts.backfill_scores --session <sid> --limit 50

旧库（difficulty 为 NULL）的兼容：按 session 时间顺序用 next_difficulty 确定性回放难度链，
起始难度取默认 3（SCORE_BAND 默认值）。这是 best-effort 近似，主要用于让旧数据也能重算；
新数据 difficulty 已落库，结果精确。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys

# 允许以模块方式运行：确保 backend 在 sys.path（直接 python scripts/backfill_scores.py 时）
sys.path.insert(0, ".")


def _load_app():
    from app.db.database import SessionLocal, init_db
    from app.db.models import TurnTrace
    from app.services import adaptation
    from sqlalchemy import select
    return SessionLocal, init_db, TurnTrace, adaptation, select


async def _recompute(row, adaptation, default_diff: int):
    """返回 (new_score, new_level, new_turn_json) 或 None（无 raw 可重算）。"""
    if not row.raw_llm_output:
        return None
    try:
        raw = json.loads(row.raw_llm_output)
    except (json.JSONDecodeError, TypeError):
        return None
    eval_node = (raw.get("evaluation") or {}) if isinstance(raw, dict) else {}
    # 优先用 5 维分项分聚合（与 harness 当轮逻辑一致）；缺分项分则退回模型整体分。
    raw_score = adaptation.aggregate_dimensions(eval_node.get("dimension_scores"))
    if raw_score is None:
        raw_score = eval_node.get("score")
    if not isinstance(raw_score, int):
        return None

    diff = row.difficulty if row.difficulty is not None else default_diff
    new_score = adaptation.calibrate_score(raw_score, diff)
    new_level = adaptation.score_to_level(new_score, diff)

    # 同步刷新 interview_turn 中已落库的校准后结果，保持存储一致
    new_turn_json = None
    if row.interview_turn:
        try:
            turn = json.loads(row.interview_turn)
            if isinstance(turn, dict):
                ev = turn.get("evaluation") or {}
                ev["score"] = new_score
                ev["overall_level"] = new_level
                turn["evaluation"] = ev
                new_turn_json = json.dumps(turn, ensure_ascii=False)
        except (json.JSONDecodeError, TypeError):
            new_turn_json = None
    return new_score, new_level, new_turn_json


async def _backfill(dry_run: bool, session_filter: str | None, limit: int | None):
    SessionLocal, init_db, TurnTrace, adaptation, select = _load_app()
    # 确保 turn_traces.difficulty 等新增列已就绪（旧库 ALTER），再查询。
    await init_db()

    async with SessionLocal() as s:
        stmt = select(TurnTrace).where(TurnTrace.raw_llm_output.isnot(None))
        if session_filter:
            stmt = stmt.where(TurnTrace.session_id == session_filter)
        stmt = stmt.order_by(TurnTrace.session_id, TurnTrace.created_at)
        if limit:
            stmt = stmt.limit(limit)
        rows = (await s.execute(stmt)).scalars().all()

    default_diff = 3  # SCORE_BAND 默认档
    total = 0
    updated = 0
    skipped = 0
    for row in rows:
        total += 1
        res = await _recompute(row, adaptation, default_diff)
        if res is None:
            skipped += 1
            continue
        new_score, new_level, new_turn_json = res
        changed = (new_score != row.score) or (new_level != row.level)
        if changed:
            updated += 1
        print(
            f"  [{row.id}] sid={row.session_id} diff={row.difficulty} "
            f"raw={_raw_score_of(row)} -> score {row.score}->{new_score} "
            f"level {row.level}->{new_level}"
            + ("  (unchanged)" if not changed else "")
            + ("  [DRY]" if dry_run else "")
        )
        if (not dry_run) and changed:
            async with SessionLocal() as ws:
                r = await ws.get(TurnTrace, row.id)
                if r is not None:
                    r.score = new_score
                    r.level = new_level
                    if new_turn_json is not None:
                        r.interview_turn = new_turn_json
                    await ws.commit()

    print(f"\n{'[DRY-RUN] ' if dry_run else ''}total={total} updated={updated} skipped={skipped}")


def _raw_score_of(row) -> str:
    try:
        raw = json.loads(row.raw_llm_output)
        return str((raw.get("evaluation") or {}).get("score"))
    except (json.JSONDecodeError, TypeError):
        return "?"


def main():
    ap = argparse.ArgumentParser(description="零成本重算历史面试评分（不改 adaptation 时结果不变）")
    ap.add_argument("--dry-run", action="store_true", help="只统计与预览，不写库")
    ap.add_argument("--session", default=None, help="只处理指定 session_id")
    ap.add_argument("--limit", type=int, default=None, help="最多处理 N 行")
    args = ap.parse_args()
    asyncio.run(_backfill(args.dry_run, args.session, args.limit))


if __name__ == "__main__":
    main()
