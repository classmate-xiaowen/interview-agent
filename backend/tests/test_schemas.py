from app.schemas.interview import InterviewTurn, Evaluation, RecordRef, CorrectedAnswer


def test_turn_defaults():
    t = InterviewTurn(question="你如何处理冲突？", question_type="behavioral")
    assert t.ask_followup is False
    assert t.references == []


def test_evaluation_score():
    e = Evaluation(score=88, covered_points=["a"], missing_points=["b"])
    assert 0 <= e.score <= 100


def test_evaluation_corrected_answer_optional():
    # 纠正模块与评分/建议解耦：默认不生成，不强制填写
    e = Evaluation(score=92, suggestions=["继续保持"])
    assert e.corrected_answer is None


def test_corrected_answer_fields():
    ca = CorrectedAnswer(
        corrected_text="用 STAR 法：当时情境是…，我采取的行动是…，结果提升 30%。",
        change_points=["用 STAR 重排结构", "补充了量化成果 30%"],
    )
    assert ca.corrected_text
    assert len(ca.change_points) == 2


def test_record_ref():
    r = RecordRef(record_id="r1", snippet="x")
    assert r.record_id == "r1"
