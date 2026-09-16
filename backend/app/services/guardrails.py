from app.schemas.interview import InterviewTurn, Evaluation


class Tripwire(Exception):
    """护栏触发：输入/输出未通过校验，需中断当前 turn。"""


_BLOCKLIST = ["ignore previous instructions", "忽略前面的指令", "system prompt"]


async def input_guardrail(msg: str) -> None:
    if not msg or not msg.strip():
        raise Tripwire("empty input")
    low = msg.lower()
    if any(b in low for b in _BLOCKLIST):
        raise Tripwire("possible prompt injection")


async def output_guardrail(turn: InterviewTurn) -> InterviewTurn:
    if not turn.question or not turn.question.strip():
        raise Tripwire("empty question in output")
    if turn.evaluation is not None:
        if not (0 <= turn.evaluation.score <= 100):
            raise Tripwire("evaluation score out of range")
    return turn
