"""成本聚合测试（模块 D）。

重点回归：分项成本之和必须等于总额（曾因逐轮四舍五入累加被放大，导致占比 >100%）。
对默认库运行，测试前后清理插入的占位行，避免污染。
"""
import asyncio
from sqlalchemy import text

from app.db.database import SessionLocal, init_db
from app.db.models import TurnTrace
from app.services import cost_service

_MARKER = "cost-test-marker"


def test_cost_aggregation_invariants():
    async def go():
        await init_db()
        async with SessionLocal() as s:
            s.add(
                TurnTrace(
                    model="deepseek-flash",
                    stage="answer",
                    tokens_in=1234,
                    tokens_out=56,
                    session_id=_MARKER,
                )
            )
            await s.commit()
        d = await cost_service.aggregate_cost()
        # 清理占位行
        async with SessionLocal() as s:
            await s.execute(text(f"DELETE FROM turn_traces WHERE session_id = '{_MARKER}'"))
            await s.commit()
        return d

    d = asyncio.run(go())

    # 回归：分项成本之和 == 总额（修复逐轮四舍五入放大）
    assert abs(sum(r["cost"] for r in d["by_stage"]) - d["totals"]["cost"]) < 1e-6
    assert abs(sum(r["cost"] for r in d["by_model"]) - d["totals"]["cost"]) < 1e-6
    # 维度非空、建议非空
    assert len(d["by_stage"]) >= 1
    assert len(d["recommendations"]) >= 1
    # 总额由真实 token 推算
    assert d["totals"]["tokens_in"] >= 0
    assert d["totals"]["tokens_out"] >= 0
