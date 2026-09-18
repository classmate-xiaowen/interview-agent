from app.services import adaptation


def test_difficulty_from_years():
    assert adaptation.difficulty_from_years(None) == 1
    assert adaptation.difficulty_from_years(0) == 1
    assert adaptation.difficulty_from_years(2) == 2
    assert adaptation.difficulty_from_years(4) == 3
    assert adaptation.difficulty_from_years(6) == 4
    assert adaptation.difficulty_from_years(10) == 5


def test_score_band_bounds():
    for d in range(1, 6):
        floor, ceil, gate = adaptation.SCORE_BAND[d]
        assert floor <= ceil
        assert gate <= floor


def test_calibrate_pulls_into_band():
    # diff=3 区间 65-80：原始 50（合格线 50）→ 应被软拉进区间
    assert adaptation.calibrate_score(50, 3) >= 65
    # 原始 95（超区间）→ 应被压回区间上限
    assert adaptation.calibrate_score(95, 3) <= 80
    # 原始 70（区间内）→ 仍在区间内
    assert 65 <= adaptation.calibrate_score(70, 3) <= 80


def test_calibrate_keeps_genuinely_low():
    # 远低于及格线：不强行拉入合格区，仅设 30 下限
    assert adaptation.calibrate_score(20, 3) == 30
    assert adaptation.calibrate_score(45, 3) == 45


def test_calibrate_monotonic():
    scores = [30, 45, 55, 65, 75, 85, 95]
    cal = [adaptation.calibrate_score(s, 3) for s in scores]
    assert cal == sorted(cal)


def test_score_to_level_band_aware():
    # diff=3 区间 65-80，中点 72.5
    assert adaptation.score_to_level(80, 3) == "优秀"
    assert adaptation.score_to_level(75, 3) == "良好"
    assert adaptation.score_to_level(66, 3) == "合格"
    assert adaptation.score_to_level(52, 3) == "待提升"
    assert adaptation.score_to_level(40, 3) == "不合格"


def test_score_calibration_mentions_brevity():
    s = adaptation.score_calibration(3, "字节跳动")
    assert "简短" in s
    # 厂风权重生效（字节→偏重算法）
    assert "算法" in s


def test_score_calibration_no_company_no_weight():
    s = adaptation.score_calibration(3, "")
    assert "该厂偏重" not in s
