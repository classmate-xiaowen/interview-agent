import logging
import time
from typing import AsyncIterator
from app.config import settings
from app.schemas.interview import (
    InterviewConfig, InterviewTurn, Evaluation, RecordRef, State, QuestionType,
)
from app.schemas.profile import UserProfile
from app.rag import store
from app.services import llm, guardrails, adaptation

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
        # 评分/出题难度档（确定性推导，随每轮校准分动态演进）
        self.diff = adaptation.difficulty_from_years(profile.years)
        self.history: list[dict] = []

    def _system(self, json_mode: bool = False) -> str:
        """拼装面试官的"系统提示词"（system prompt）。

        把面试官风格（高压/温和/深挖，见 _STYLE_PROMPT）与候选人档案上下文
        合并成一段固定前置指令。

        - json_mode=True：用于结构化 EVAL 调用（chat_structured），要求模型
          严格按 JSON Schema 回复且必须带 references。
        - json_mode=False（默认）：用于流式出题/总结（stream_text），只输出
          问题或点评的纯文本（Markdown 允许），禁止输出 JSON。

        注意：流式路径若带 JSON 指令，模型会原样吐出
        `{"question": "...", "references": []}` 文本，被当作 token 直接渲染到
        前端，造成「页面显示 raw JSON」的 bug。且最终 references 由 _retrieve()
        独立检索得到，模型端的 references 本就被覆盖，JSON 指令纯属多余且有害。
        """
        p = self.profile
        ctx = (f"候选人：技能={p.skills}，年限={p.years}，目标岗位={p.target_role}，"
               f"目标公司={','.join(p.target_companies)}，薄弱点={p.weaknesses}，"
               f"市场环境={p.market_context}")
        if json_mode:
            return (f"{_STYLE_PROMPT[self.config.interviewer_style]}\n{ctx}\n"
                    f"严格按给定 JSON Schema 回复，必须包含 references（可空数组）。")
        return (f"{_STYLE_PROMPT[self.config.interviewer_style]}\n{ctx}\n"
                f"仅输出面试问题或点评的纯文本（可用 Markdown 的加粗/列表组织），"
                f"不要输出 JSON。\n"
                f"重要：每轮只提【一个】问题，等待候选人回答后再继续提问，"
                f"绝不要在一次回复中罗列多个问题。")

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
                "请提出第一道面试问题。只输出【一个】问题本身，"
                "不要附带多个问题或候选清单，等候选人回答后再继续。可使用 Markdown 的加粗强调。",
                history=self.history,
            )
        else:
            await guardrails.input_guardrail(user_msg)
            eval_turn = await llm.chat_structured(
                self._system(json_mode=True),
                f"EVAL 用户回答：{user_msg}\n"
                f"请作为国内大厂技术面试官对该回答评分，并决定是否需要追问（ask_followup）。\n"
                f"评分维度（国内大厂真实 5 维）：①问题拆解与边界确认 ②技术理解深度"
                f"（真懂还是套方案/背八股，能结合场景讲清 trade-off 才得分）"
                f"③编码/表达质量（讲清思路即达标，简短但切中要害不扣分）"
                f"④沟通与协作感 ⑤心智与团队匹配。\n"
                f"{adaptation.score_calibration(self.diff, self.config.target_company)}\n"
                f"若回答有改进空间，请在 evaluation.corrected_answer 中给出："
                f"corrected_text=改写后的完整回答（更准确/规范、贴合 STAR），"
                f"change_points=相对原回答的具体修改点列表（每条聚焦一处改动，不要重复 suggestions 的笼统建议）；"
                f"若回答已较好则 corrected_answer 置为 null。",
                InterviewTurn,
                history=self.history,
            )
            evaluation = eval_turn.evaluation or Evaluation(score=60)
            # 国内化分级校准：软拉到难度档目标区间 + 确定性 5 级定性结论（防漂移、偏宽松）
            evaluation.score = adaptation.calibrate_score(evaluation.score, self.diff)
            evaluation.overall_level = adaptation.score_to_level(evaluation.score, self.diff)
            self.diff = adaptation.next_difficulty(self.diff, evaluation.score)[0]
            self.questions_asked += 1
            ask_followup = bool(eval_turn.ask_followup)
            if self.questions_asked >= settings.max_questions:
                self.state = State.SUMMARY
                qtype = "behavioral"
                stream = llm.stream_text(
                    self._system(),
                    "面试结束，请输出总体点评与改进行动建议（Markdown 文本，可含标题与列表）。",
                    history=self.history,
                )
            elif ask_followup and eval_turn.followup_question:
                qtype = "follow_up"
                stream = _const_chunks(eval_turn.followup_question, 6)
            else:
                qtype = "behavioral"
                stream = llm.stream_text(
                    self._system(),
                    "请提出下一道新的面试问题。同样只输出【一个】问题本身，"
                    "不要列出多个问题，等待候选人回答后再继续。",
                    history=self.history,
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
