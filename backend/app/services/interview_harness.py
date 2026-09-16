import logging
import time
from app.config import settings
from app.schemas.interview import (
    InterviewConfig, InterviewTurn, Evaluation, RecordRef, State,
)
from app.schemas.profile import UserProfile
from app.rag import store
from app.services import llm, guardrails

_STYLE_PROMPT = {
    "pressure": "你是高压型面试官，追问犀利、要求严谨。",
    "gentle": "你是温和引导型面试官，鼓励候选人展开。",
    "deep": "你是技术深挖型面试官，关注原理与边界。",
}


async def _retrieve(config: InterviewConfig, query: str) -> list[RecordRef]:
    fmeta = {}
    if config.target_company:
        fmeta["company"] = config.target_company
    hits = await store.query_chunks(query, n=3, filter_meta=fmeta or None)
    return [RecordRef(record_id=h["metadata"].get("record_id", h["id"]), snippet=h["text"][:200])
            for h in hits]


class InterviewSession:
    def __init__(self, config: InterviewConfig, profile: UserProfile):
        self.config = config
        self.profile = profile
        self.state = State.ASKING
        self.questions_asked = 0
        self.history: list[dict] = []

    def _system(self) -> str:
        p = self.profile
        ctx = (f"候选人：技能={p.skills}，年限={p.years}，目标岗位={p.target_role}，"
               f"目标公司={','.join(p.target_companies)}，薄弱点={p.weaknesses}，"
               f"市场环境={p.market_context}")
        return (f"{_STYLE_PROMPT[self.config.interviewer_style]}\n{ctx}\n"
                f"严格按给定 JSON Schema 回复，必须包含 references（可空数组）。")

    async def start(self) -> InterviewTurn:
        self.state = State.ASKING
        t0 = time.time()
        refs = await _retrieve(self.config, "开场自我介绍类问题")
        turn = await llm.chat_structured(
            self._system(),
            "请提出第一道面试问题（evaluation 为 null）。",
            InterviewTurn,
        )
        turn.references = refs
        await guardrails.output_guardrail(turn)
        self.questions_asked += 1
        self.history.append({"role": "assistant", "content": turn.question})
        logging.info("turn start sid=? out=%d refs=%d ms=%.0f",
                     len(turn.question), len(refs), (time.time() - t0) * 1000)
        return turn

    async def answer(self, user_msg: str) -> InterviewTurn:
        t0 = time.time()
        await guardrails.input_guardrail(user_msg)
        # 1) 评测上一轮回答
        eval_turn = await llm.chat_structured(
            self._system(),
            f"EVAL 用户回答：{user_msg}\n请对该回答评分并决定是否需要追问（ask_followup）。",
            InterviewTurn,
        )
        evaluation: Evaluation = eval_turn.evaluation or Evaluation(score=60)
        # 2) 决定下一步
        if self.questions_asked >= settings.max_questions:
            self.state = State.SUMMARY
            summary = await llm.chat_structured(
                self._system(),
                "面试结束，给出总体点评与改进建议（question 写总结，evaluation 写总评）。",
                InterviewTurn,
            )
            summary.evaluation = evaluation
            await guardrails.output_guardrail(summary)
            return summary
        follow_up = eval_turn.ask_followup
        if follow_up and eval_turn.followup_question:
            next_q = eval_turn.followup_question
            qtype = "follow_up"
        else:
            nxt = await llm.chat_structured(
                self._system(),
                "请提出下一道新的面试问题（evaluation 为 null）。",
                InterviewTurn,
            )
            next_q = nxt.question
            qtype = nxt.question_type
        refs = await _retrieve(self.config, next_q)
        out = InterviewTurn(question=next_q, question_type=qtype,
                            references=refs, evaluation=evaluation,
                            ask_followup=bool(follow_up))
        await guardrails.output_guardrail(out)
        self.questions_asked += 1
        self.history.append({"role": "user", "content": user_msg})
        self.history.append({"role": "assistant", "content": out.question})
        self.state = State.ASKING
        logging.info("turn ans sid=? in=%d out=%d score=%s refs=%d ms=%.0f",
                     len(user_msg), len(out.question),
                     out.evaluation.score if out.evaluation else None,
                     len(refs), (time.time() - t0) * 1000)
        return out
