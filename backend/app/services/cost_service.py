"""成本聚合：把已落库的 turn_traces token 折算成可决策的成本视图（模块 D）。

聚合维度：总览 / 按模型 / 按阶段(kickoff|answer|summary) / 按天 / Top 会话，
并给出基于数据的决策建议（如高成本阶段可路由到更便宜模型、换模型可省比例等）。

实现：一次性取出全部 turn_traces 行后在 Python 内聚合（数据量小、且需跨维度按真实模型核算成本，
避免 SQL 分组丢失每行的模型归属）。
"""
from __future__ import annotations

from sqlalchemy import select

from app.db.database import SessionLocal
from app.db.models import TurnTrace
from app.services import pricing


def _acc(bucket: dict, key: str, tokens_in: int, tokens_out: int, cost: float) -> None:
    b = bucket.setdefault(key, {"tokens_in": 0, "tokens_out": 0, "turns": 0, "cost": 0.0})
    b["tokens_in"] += tokens_in
    b["tokens_out"] += tokens_out
    b["turns"] += 1
    b["cost"] += cost  # 累计原始浮点，避免逐轮四舍五入放大误差


def _to_rows(bucket: dict, sort_by: str = "cost") -> list[dict]:
    rows = [
        {
            "key": k,
            "tokens_in": v["tokens_in"],
            "tokens_out": v["tokens_out"],
            "turns": v["turns"],
            "cost": round(v["cost"], 4),
        }
        for k, v in bucket.items()
    ]
    rows.sort(key=lambda r: r[sort_by], reverse=True)
    return rows


async def aggregate_cost() -> dict:
    async with SessionLocal() as s:
        rows = (
            await s.execute(
                select(
                    TurnTrace.model,
                    TurnTrace.tokens_in,
                    TurnTrace.tokens_out,
                    TurnTrace.stage,
                    TurnTrace.created_at,
                    TurnTrace.session_id,
                )
            )
        ).all()

    by_model: dict[str, dict] = {}
    by_stage: dict[str, dict] = {}
    by_day: dict[str, dict] = {}
    by_session: dict[str, dict] = {}
    total_in = total_out = 0

    for model, tin, tout, stage, created_at, sid in rows:
        model = model or "unknown"
        tin = int(tin or 0)
        tout = int(tout or 0)
        total_in += tin
        total_out += tout
        # 原始成本（不四舍五入），按真实模型单价核算
        in_p, out_p = pricing.price_for(model)
        cost = tin / 1_000_000 * in_p + tout / 1_000_000 * out_p
        _acc(by_model, model, tin, tout, cost)
        _acc(by_stage, stage or "unknown", tin, tout, cost)
        _acc(by_day, (created_at or "")[:10] or "unknown", tin, tout, cost)
        if sid:
            _acc(by_session, sid, tin, tout, cost)

    # 总额由各维度原始成本汇总后仅在此处四舍五入一次，保证与分项之和一致
    total_cost = round(sum(b["cost"] for b in by_model.values()), 4)
    sessions_count = len(by_session)

    model_rows = _to_rows(by_model)
    stage_rows = _to_rows(by_stage)
    day_rows = sorted(_to_rows(by_day), key=lambda r: r["key"])  # 按日期升序看趋势
    session_rows = _to_rows(by_session)[:10]

    recommendations = _recommend(total_cost, model_rows, stage_rows, session_rows)

    return {
        "totals": {
            "tokens_in": total_in,
            "tokens_out": total_out,
            "turns": len(rows),
            "sessions": sessions_count,
            "cost": total_cost,
        },
        "by_model": model_rows,
        "by_stage": stage_rows,
        "by_day": day_rows,
        "top_sessions": session_rows,
        "recommendations": recommendations,
        "currency": "CNY",
    }


def _recommend(total_cost: float, model_rows: list[dict], stage_rows: list[dict],
               session_rows: list[dict]) -> list[str]:
    recs: list[str] = []
    if not model_rows:
        return ["暂无成本数据：跑过面试后这里会显示按模型/阶段/日期的 token 成本与决策建议。"]

    primary = model_rows[0]
    in_p, out_p = pricing.price_for(primary["key"])
    recs.append(
        f"主模型「{primary['key']}」单价 ≈ 输入 ¥{in_p}/1M、输出 ¥{out_p}/1M（近似值，请以真实账单校准）。"
    )

    if total_cost > 0:
        recs.append(
            f"累计成本约 ¥{total_cost:.2f}，共 {sum(m['turns'] for m in model_rows)} 轮；"
            f"单轮平均约 ¥{total_cost / max(1, sum(m['turns'] for m in model_rows)):.4f}。"
        )

    # 最贵阶段
    if len(stage_rows) > 1:
        top_stage = stage_rows[0]
        share = top_stage["cost"] / total_cost * 100 if total_cost else 0
        recs.append(
            f"「{top_stage['key']}」阶段成本占比最高（{share:.0f}%）。该阶段（如首题/总结）"
            f"对模型能力要求较低，可考虑路由到更便宜模型以降本。"
        )

    # 换最便宜模型可省比例
    if len(model_rows) >= 1:
        # 取所有已知单价里最低的输出单价模型作为参照（同 token 结构）
        cheapest_out = min(pricing.price_for(m["key"])[1] for m in model_rows)
        current_out = pricing.price_for(primary["key"])[1]
        if cheapest_out < current_out and total_cost > 0:
            save_pct = (current_out - cheapest_out) / current_out * 100
            recs.append(
                f"若把全部流量切到单价最低档模型（输出 ¥{cheapest_out}/1M），"
                f"按当前 token 结构预计可省约 {save_pct:.0f}%。"
            )

    # 最贵会话
    if session_rows:
        top_s = session_rows[0]
        q = top_s["cost"] / total_cost * 100 if total_cost else 0
        recs.append(
            f"最贵会话 {top_s['key'][:8]}… 累计 ¥{top_s['cost']:.2f}，占总额 {q:.0f}%，"
            f"可单独复盘其长度/追问轮数是否异常。"
        )

    return recs
