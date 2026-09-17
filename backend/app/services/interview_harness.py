import logging
import time
from typing import AsyncIterator
from app.config import settings
from app.schemas.interview import (
    InterviewConfig, InterviewTurn, Evaluation, RecordRef, State, QuestionType,
)
from app.schemas.profile import UserProfile
from app.rag import store
from app.services import llm, guardrails

_STYLE_PROMPT: dict[str, str] = {
    "pressure": "你是高压型面试官，追问犀利、要求严谨。",
    "gentle": "你是温和引导型面试官，鼓励候选人展开。",
    "deep": "你是技术深挖型面试官，关注原理与边界。",
}


async def _retrieve(config: InterviewConfig, query: str) -> list[RecordRef]:
    """根据查询从向量库检索相关题库片段，作为面试官出题/追问的参考素材。

    - 若配置了目标公司（config.target_company），则按 company 元数据过滤，
      只召回该公司相关的题目片段；否则不限公司。
    - 取 top-3 命中，每条转成 RecordRef（含 record_id 与截断到 200 字的 snippet）。
    - 返回结果会挂到 InterviewTurn.references，给候选/面试官提供上下文支撑。
    """
    fmeta = {}
    if config.target_company:
        fmeta["company"] = config.target_company
    hits = await store.query_chunks(query, n=3, filter_meta=fmeta or None)
    return [RecordRef(record_id=h["metadata"].get("record_id", h["id"]), snippet=h["text"][:200])
            for h in hits]


async def _const_chunks(text: str, size: int = 6) -> AsyncIterator[str]:
    """将已生成的文本按小段 yield，用于追问等无需重新调用 LLM 的场景。"""
    for i in range(0, len(text), size):
        yield text[i:i + size]


class InterviewSession:
    def __init__(self, config: InterviewConfig, profile: UserProfile):
        """初始化一次面试会话：保存配置与档案，并重置会话状态。

        - config：面试官风格、目标公司、题目数量上限等。
        - profile：候选人技能/年限/目标岗位等上下文，用于系统提示。
        - 初始化后 state=ASKING（出题态）、questions_asked=0、history 为空。
        """
        self.config = config
        self.profile = profile
        self.state = State.ASKING
        self.questions_asked = 0
        self.history: list[dict] = []

    def _system(self) -> str:
        """拼装面试官的"系统提示词"（system prompt）。

        把面试官风格（高压/温和/深挖，见 _STYLE_PROMPT）与候选人档案上下文
        合并成一段固定前置指令，要求模型严格按 JSON Schema 回复且必须带 references。
        每次调用 LLM 都会带上它，保证面试风格与个性化一致。
        """
        p = self.profile
        ctx = (f"候选人：技能={p.skills}，年限={p.years}，目标岗位={p.target_role}，"
               f"目标公司={','.join(p.target_companies)}，薄弱点={p.weaknesses}，"
               f"市场环境={p.market_context}")
        return (f"{_STYLE_PROMPT[self.config.interviewer_style]}\n{ctx}\n"
                f"严格按给定 JSON Schema 回复，必须包含 references（可空数组）。")

    async def stream_answer(self, user_msg: str, kickoff: bool = False) -> AsyncIterator[dict]:
        """流式驱动一轮对话，逐 token 推送问题文本，末尾推送完整 InterviewTurn。

        事件协议（text/event-stream）：
          {"type": "token", "text": "<片段>"}   流式问题正文
          {"type": "turn",  "turn":  <InterviewTurn>}  # 完整结构化结果（评分/引用）
        异常由调用方（router）兜底封装为 {"type": "error"}。
        """
        t0 = time.time()
        if kickoff:
            self.state = State.ASKING
            qtype: QuestionType = "behavioral"
            evaluation: Evaluation | None = None
            ask_followup = False
            stream = llm.stream_text(
                self._system(),
                "请提出第一道面试问题（仅输出问题文本，可用 Markdown 的加粗/列表组织提示）。",
            )
        else:
            await guardrails.input_guardrail(user_msg)
            eval_turn = await llm.chat_structured(
                self._system(),
                f"EVAL 用户回答：{user_msg}\n请对该回答评分并决定是否需要追问（ask_followup）。",
                InterviewTurn,
            )
            evaluation = eval_turn.evaluation or Evaluation(score=60)
            self.questions_asked += 1
            ask_followup = bool(eval_turn.ask_followup)
            if self.questions_asked >= settings.max_questions:
                self.state = State.SUMMARY
                qtype = "behavioral"
                stream = llm.stream_text(
                    self._system(),
                    "面试结束，请输出总体点评与改进行动建议（Markdown 文本，可含标题与列表）。",
                )
            elif ask_followup and eval_turn.followup_question:
                qtype = "follow_up"
                stream = _const_chunks(eval_turn.followup_question, 6)
            else:
                qtype = "behavioral"
                stream = llm.stream_text(
                    self._system(),
                    "请提出下一道新的面试问题（仅输出问题文本，可使用 Markdown 的列表/加粗组织提示）。",
                )

        collected: list[str] = []
        async for piece in stream:
            if not piece:
                continue
            collected.append(piece)
            yield {"type": "token", "text": piece}
        question_text = "".join(collected).strip()

        refs = await _retrieve(self.config, question_text or "面试问题")
        out = InterviewTurn(
            question=question_text,
            question_type=qtype,
            references=refs,
            evaluation=evaluation,
            ask_followup=ask_followup,
        )
        await guardrails.output_guardrail(out)
        if not kickoff:
            self.history.append({"role": "user", "content": user_msg})
        self.history.append({"role": "assistant", "content": question_text})
        if self.state != State.SUMMARY:
            self.state = State.ASKING
        logging.info("turn %s sid=? in=%d out=%d score=%s refs=%d ms=%.0f",
                     "kickoff" if kickoff else "answer",
                     len(user_msg), len(question_text),
                     out.evaluation.score if out.evaluation else None,
                     len(refs), (time.time() - t0) * 1000)
        yield {"type": "turn", "turn": out.model_dump()}
