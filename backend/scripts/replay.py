"""可观测回放 / eval harness 引擎（模块 B + C）。

设计：把"面试点评质量"变成可度量、可回归的工程对象。
- 离线（默认 `--mode fake`，零 token）：用确定性 fake LLM 跑完整 `InterviewSession.stream_answer`
  流水线（输入护栏 → EVAL 结构化 → 校准 → 难度演进 → 输出护栏 → trace 落库），验证点评链路在
  改动后仍稳定；fake 只替换 LLM 的"原始分"，校准/难度/护栏全部走真实代码。
- 真模型（`--mode live`，需 OPENAI_API_KEY）：跑真实 LLM 端到端质量回归。
- 基线漂移：与 `eval/baseline.json`（上次结果）对比，分数偏移超阈值即告警（防漂移，NFR-7）。

用法：
    python -m scripts.replay --mode fake
    python -m scripts.replay --mode live
    python -m scripts.replay --update-baseline   # 把本次结果写为新基线
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from typing import Any

# 确保 backend 根目录在 sys.path，便于 `app` / `scripts` 包导入。
_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from app.rag import store as store_mod  # noqa: E402
from app.schemas.interview import Evaluation, InterviewConfig, InterviewTurn  # noqa: E402
from app.schemas.profile import UserProfile  # noqa: E402
from app.services import llm as llm_mod  # noqa: E402
from app.services.interview_harness import InterviewSession  # noqa: E402

_GOLDEN_PATH = os.path.join(_BACKEND, "eval", "golden.jsonl")
_BASELINE_PATH = os.path.join(_BACKEND, "eval", "baseline.json")
_REPORT_PATH = os.path.join(_BACKEND, "eval", "eval_report.json")
DRIFT_THRESHOLD = 5  # 分数漂移告警阈值（分）

# fake 模式下供 fake_chat_structured 读取的"模型原始分"容器。
_FAKE_STATE: dict[str, int] = {"raw_score": 70}


async def fake_chat_structured(system, user, response_model, model=None, history=None):
    """fake 模式：返回确定的 InterviewTurn（仅替换 LLM 的"原始分"，校准层走真实代码）。

    产出与真实 EVAL 一致的 5 维分项分（全部=raw），使 aggregate_dimensions 聚合后仍得到
    raw，从而校准结果与改动前一致——fake 仅替换"原始分"这一不可再生输入。
    """
    raw = _FAKE_STATE.get("raw_score", 70)
    from app.services.adaptation import DIMENSION_WEIGHTS
    dims = {k: raw for k in DIMENSION_WEIGHTS}
    return InterviewTurn(
        question="",
        question_type="technical",
        evaluation=Evaluation(score=raw, dimension_scores=dims),
        ask_followup=raw >= 70,
        followup_question="请再深入讲一下你的实现细节与取舍。" if raw >= 70 else None,
    ), None


async def fake_stream(system, user, model=None, history=None):
    """fake 模式：流式出题的异步生成器替身。"""
    yield "请结合你提到的经验，展开讲一下具体的实现与权衡。"


async def fake_query_chunks(text, n=5, filter_meta=None):
    """fake 模式：返回固定检索命中（验证 NFR-7 引用必填）。"""
    return [
        {"id": "r1", "text": "示例知识点一：缓存穿透与布隆过滤器", "metadata": {"record_id": "rec-1"}, "distance": 0.1},
        {"id": "r2", "text": "示例知识点二：超时控制与熔断", "metadata": {"record_id": "rec-2"}, "distance": 0.2},
        {"id": "r3", "text": "示例知识点三：一致性方案", "metadata": {"record_id": "rec-3"}, "distance": 0.3},
    ]


def _install_fakes() -> None:
    llm_mod.chat_structured = fake_chat_structured  # type: ignore[assignment]
    llm_mod.stream_text = fake_stream  # type: ignore[assignment]
    store_mod.query_chunks = fake_query_chunks  # type: ignore[assignment]


async def run_entry(entry: dict, live: bool) -> dict:
    """跑单条 golden：先 kickoff 建场，再 answer 评估，返回最终 answer turn 的结果。"""
    if not live:
        _install_fakes()
    _FAKE_STATE["raw_score"] = entry.get("raw_score", 70)

    profile = UserProfile(**entry.get("profile", {}))
    config = InterviewConfig(**entry.get("config", {}))

    # live 模式只 fake 检索（避免依赖已灌库的向量库），LLM 走真实调用。
    if live:
        store_mod.query_chunks = fake_query_chunks  # type: ignore[assignment]

    sess = InterviewSession(config, profile)
    result: dict[str, Any] = {"id": entry["id"], "error": None}

    try:
        # 1) kickoff 建场（不评估，仅建状态/历史）
        async for ev in sess.stream_answer("", kickoff=True, session_id="eval-replay"):
            if ev["type"] == "error":
                result["error"] = ev["message"]
                return result
        # 2) answer 评估
        out = None
        async for ev in sess.stream_answer(entry["user_answer"], kickoff=False, session_id="eval-replay"):
            if ev["type"] == "turn":
                out = ev["turn"]
            elif ev["type"] == "error":
                result["error"] = ev["message"]
                return result
        if out is None:
            result["error"] = "no turn produced"
            return result
        result["turn"] = out
        result["score"] = (out.get("evaluation") or {}).get("score")
        result["level"] = (out.get("evaluation") or {}).get("overall_level")
        result["followup"] = out.get("ask_followup")
        result["refs"] = len(out.get("references") or [])
    except Exception as e:  # 单条失败不影响整体
        result["error"] = f"{type(e).__name__}: {e}"
    return result


def check_entry(entry: dict, result: dict) -> list[str]:
    """对单条结果做断言，返回问题列表（空=通过）。"""
    issues: list[str] = []
    if result.get("error"):
        return [f"run error: {result['error']}"]
    out = result["turn"]
    exp = entry["expected"]
    ev = out.get("evaluation")
    if not ev:
        return ["evaluation missing"]
    score = ev.get("score")
    level = ev.get("overall_level")
    if score is None or not (exp["min_score"] <= score <= exp["max_score"]):
        issues.append(f"score {score} not in [{exp['min_score']},{exp['max_score']}]")
    if level not in exp["level_in"]:
        issues.append(f"level {level} not in {exp['level_in']}")
    if len(out.get("references") or []) == 0:
        issues.append("references empty (NFR-7 引用必填)")
    if "expect_followup" in exp and result.get("followup") != exp["expect_followup"]:
        issues.append(f"followup {result.get('followup')} != {exp['expect_followup']}")
    try:
        json.dumps(out)
    except (TypeError, ValueError):
        issues.append("turn not json-serializable (NFR-7 可解析)")
    return issues


def load_golden(path: str = _GOLDEN_PATH) -> list[dict]:
    entries: list[dict] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries


def load_baseline(path: str = _BASELINE_PATH) -> dict:
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def run_all(entries: list[dict], live: bool) -> list[dict]:
    results: list[dict] = []
    for entry in entries:
        result = asyncio.run(run_entry(entry, live))
        result["issues"] = check_entry(entry, result)
        results.append(result)
    return results


def compare_baseline(results: list[dict], baseline: dict) -> None:
    """与基线对比，分数漂移超阈值追加到 issues。"""
    for r in results:
        if r.get("error") or r.get("score") is None:
            continue
        base = baseline.get(r["id"])
        if not base or base.get("score") is None:
            continue
        delta = r["score"] - base["score"]
        if abs(delta) > DRIFT_THRESHOLD:
            r["issues"].append(f"drift {delta:+d} vs baseline {base['score']}")


def write_report(results: list[dict], baseline: dict, path: str = _REPORT_PATH) -> dict:
    passed = sum(1 for r in results if not r["issues"])
    drifted = sum(1 for r in results if any("drift" in i for i in r["issues"]))
    report = {
        "total": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "drifted": drifted,
        "entries": [
            {
                "id": r["id"],
                "score": r.get("score"),
                "level": r.get("level"),
                "followup": r.get("followup"),
                "refs": r.get("refs"),
                "error": r.get("error"),
                "issues": r.get("issues", []),
                "baseline_score": (baseline.get(r["id"]) or {}).get("score"),
            }
            for r in results
        ],
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    return report


def write_baseline(results: list[dict], path: str = _BASELINE_PATH) -> None:
    base = {r["id"]: {"score": r.get("score"), "level": r.get("level")} for r in results}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(base, f, ensure_ascii=False, indent=2)


def _print_summary(report: dict, mode: str) -> None:
    print(f"\n=== eval replay ({mode}) ===")
    print(f"total={report['total']} passed={report['passed']} failed={report['failed']} drifted={report['drifted']}")
    for e in report["entries"]:
        flag = "OK " if not e["issues"] else "FAIL"
        print(f"  [{flag}] {e['id']:>4} score={e['score']} level={e['level']} "
              f"base={e['baseline_score']} refs={e['refs']} {('| ' + '; '.join(e['issues'])) if e['issues'] else ''}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="eval harness replay")
    parser.add_argument("--mode", choices=["fake", "live"], default="fake")
    parser.add_argument("--update-baseline", action="store_true", help="把本次结果写为新基线")
    parser.add_argument("--golden", default=_GOLDEN_PATH)
    args = parser.parse_args(argv)

    entries = load_golden(args.golden)
    results = run_all(entries, live=(args.mode == "live"))

    baseline = load_baseline()
    has_baseline = bool(baseline)
    if has_baseline:
        compare_baseline(results, baseline)

    report = write_report(results, baseline)
    _print_summary(report, args.mode)

    if args.update_baseline or not has_baseline:
        write_baseline(results)
        print(f"(baseline {'updated' if args.update_baseline else 'created'})")

    # 退出码：有失败或漂移则非 0，便于 CI 拦截。
    if report["failed"] > 0 or report["drifted"] > 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
