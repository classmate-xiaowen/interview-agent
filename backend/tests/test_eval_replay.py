import os
import sys

# 让 `scripts` 包可导入（backend 根在 sys.path 时，scripts 已是包）。
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts.replay import check_entry, load_golden, run_all  # noqa: E402


def test_golden_replay_fake_covers_all_entries():
    """fake 回放应覆盖全部 golden 条目且不抛错。"""
    entries = load_golden()
    assert len(entries) >= 12, "golden 样例集应至少覆盖 12 条（各难度档/风格/优差回答）"
    results = run_all(entries, live=False)
    assert len(results) == len(entries)


def test_golden_replay_fake_all_pass():
    """fake 回放：校准层 + 全流程在改动后仍稳定（防漂移的 CI 闸门）。"""
    entries = load_golden()
    results = run_all(entries, live=False)
    failed = [(r["id"], r.get("error"), r.get("issues")) for r in results if r.get("issues")]
    assert not failed, "golden 回放失败:\n" + "\n".join(
        f"  {i}: err={err} issues={iss}" for i, err, iss in failed
    )


def test_golden_replay_asserts_references_and_parse():
    """NFR-7：每条点评都带引用且可 JSON 序列化。"""
    entries = load_golden()
    results = run_all(entries, live=False)
    for r in results:
        assert not r.get("error"), r["error"]
        assert (r["turn"].get("references") or []), f"{r['id']} references 为空"
