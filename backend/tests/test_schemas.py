from app.schemas.interview import InterviewTurn, Evaluation, RecordRef


def test_turn_defaults():
    t = InterviewTurn(question="你如何处理冲突？", question_type="behavioral")
    assert t.ask_followup is False
    assert t.references == []


def test_evaluation_score():
    e = Evaluation(score=88, covered_points=["a"], missing_points=["b"])
    assert 0 <= e.score <= 100


def test_record_ref():
    r = RecordRef(record_id="r1", snippet="x")
    assert r.record_id == "r1"
