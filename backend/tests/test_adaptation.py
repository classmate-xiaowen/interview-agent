import pytest

from app.services.adaptation import (
    direction_hint,
    next_difficulty,
    salary_to_baseline,
)


def test_salary_to_baseline_bands():
    # 输入单位为千/月，区间 7k 起步 ~ 35k 封顶；分档后整体 ×0.65 再压一档：
    # 分档 <12k→1, 12-18k→2, 18-25k→3, 25-30k→4, >=30k→5
    # 下调后：1→1, 2→1, 3→2, 4→3, 5→3
    assert salary_to_baseline(8, 10, "不限") == 1     # 9k  → 分档1 → 1
    assert salary_to_baseline(15, 18, "不限") == 1    # 16.5k → 分档2 → 1
    assert salary_to_baseline(20, 25, "不限") == 2    # 22.5k → 分档3 → 2
    assert salary_to_baseline(25, 30, "不限") == 3    # 27.5k → 分档4 → 3
    assert salary_to_baseline(32, 35, "不限") == 3    # 33.5k → 分档5 → 3（封顶压一档）


def test_salary_to_baseline_tier_bias():
    # 分档下调后再叠加档位偏置：大厂 +1；创业 -1；外企/中厂 0
    assert salary_to_baseline(15, 18, "大厂") == 2    # 分档2→1 +1
    assert salary_to_baseline(15, 18, "中厂") == 1    # 分档2→1 +0
    assert salary_to_baseline(15, 18, "创业") == 1    # 分档2→1 -1 封底
    assert salary_to_baseline(32, 35, "外企") == 3    # 分档5→3 +0


def test_salary_to_baseline_clamp():
    assert salary_to_baseline(5, 6, "创业") >= 1      # 低于起步档仍封底 1
    assert salary_to_baseline(50, 60, "大厂") <= 5    # 高于封顶档封顶 5


def test_salary_to_baseline_single_value():
    # 只给下限时以 lower 为中点（千/月）
    assert salary_to_baseline(25, 0, "不限") == 3     # 25k → 分档4 → 3


def test_next_difficulty_up():
    assert next_difficulty(3, 80) == (4, "升级/换方向")
    assert next_difficulty(5, 90) == (5, "升级/换方向")  # 封顶


def test_next_difficulty_down():
    assert next_difficulty(3, 40) == (2, "降级/补基础")
    assert next_difficulty(1, 10) == (1, "降级/补基础")  # 封底


def test_next_difficulty_keep():
    assert next_difficulty(3, 60) == (3, "追问关键细节")
    assert next_difficulty(3, 50) == (3, "追问关键细节")  # 边界 50 属保持
    assert next_difficulty(3, 74) == (3, "追问关键细节")


def test_direction_hint_high_diff_technical():
    h = direction_hint(32, 35, "大厂", "", "并发编程", "后端", 5)
    assert "technical" in h
    assert "后端" in h
    assert "并发编程" in h
    assert "k/月" in h


def test_direction_hint_market_defense():
    h = direction_hint(20, 25, "不限", "当前市场降温，hc 很少", "", "前端", 3)
    assert "偏冷" in h
    assert "前端" in h


def test_direction_hint_low_diff_basic():
    h = direction_hint(12, 15, "创业", "", "", "测试", 2)
    assert "基础" in h


def test_direction_hint_boom_ai():
    h = direction_hint(32, 35, "大厂", "AI 岗位扩招，行情回暖", "", "算法", 4)
    assert "偏热" in h
    assert "算法" in h
