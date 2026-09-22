"""LLM 单价表（CNY / 每 1M tokens），用于把落库的 token 折算成成本（决策依据）。

注意：以下为公开发布价的近似值，仅用于趋势/占比估算，不应替代真实账单。
若换了模型或厂商调价，请在此更新。键为模型名子串（大小写不敏感），命中第一个即采用；
未命中则用 DEFAULT。
"""
from __future__ import annotations

# (输入单价, 输出单价) 单位：人民币元 / 1M tokens
PRICING_CNY_PER_1M: dict[str, tuple[float, float]] = {
    "deepseek": (1.0, 2.0),        # deepseek-chat / flash / reasoner 近似
    "gpt-4o-mini": (1.1, 4.3),
    "gpt-4o": (18.0, 72.0),
    "gpt-4": (18.0, 72.0),
    "gpt-3.5": (1.0, 2.0),
    "claude": (15.0, 75.0),
    "qwen": (0.4, 1.2),
    "glm": (1.0, 1.0),
    "moonshot": (1.0, 2.0),
    "kimi": (1.0, 2.0),
    "text-embedding": (0.02, 0.02),
}

DEFAULT_CNY_PER_1M: tuple[float, float] = (1.0, 2.0)


def price_for(model: str | None) -> tuple[float, float]:
    """按模型名（子串匹配，不敏感）返回 (输入单价, 输出单价)。"""
    name = (model or "").lower()
    for key, val in PRICING_CNY_PER_1M.items():
        if key in name:
            return val
    return DEFAULT_CNY_PER_1M


def estimate_cost(model: str | None, tokens_in: int, tokens_out: int) -> float:
    """估算一次调用的成本（CNY）。token 为 0 时返回 0。"""
    tin = max(0, int(tokens_in))
    tout = max(0, int(tokens_out))
    if tin == 0 and tout == 0:
        return 0.0
    in_p, out_p = price_for(model)
    return round(tin / 1_000_000 * in_p + tout / 1_000_000 * out_p, 4)
