"""面试动态适配：薪资 × 市场 → 难度档位 + 出题方向（确定性纯函数，可单测）。

设计原则：难度与方向由确定性规则驱动（可控、不漂移），具体题目文本仍交给 LLM。
后续由 interview_harness 调用，不直接依赖 DB / LLM。

阈值校准依据（2026 实测行情，避免拍脑袋）：
- 程序员薪资分级（CSDN 2026 手册）：初级 10-20w / 中级 20-40w / 高级 40-70w / 专家 50-200w。
- 校招真实开奖（小林coding 2026）：大厂技术岗总包 31.5~79w（多数起步 31-40w，SSP 冲 60w+），
  中厂 22.5~49w。说明「同薪资下大厂对应更低经验层级」——大厂/外企总包虚高，故难度主要靠
  薪资分档决定，档位偏置仅作小幅修正，避免把数字顶到专家级。
- 招聘行情（脉脉 2026）：结构性回暖、AI 岗暴涨、传统互联网降温分化，行情关键词据此扩展。
- 分岗位薪资（CSDN MCP 社区 2026 年报综合）：算法/大模型同级别薪资明显高于普通开发，测试/运维偏低。
  故引入角色维度——同薪资对不同岗意味不同资深度（算法同薪更初级、测试同薪更资深），见 ROLE_PAY_OFFSET。

薪资单位：用户输入为「千/月」（如 25 表示 25k/月）。难度档位先按月薪分档（7k 起步 ~ 35k 封顶
→ 1-5），再整体 ×DIFFICULTY_SCALE(0.65) 下调一档，最后叠加档位偏置；方向提示里附「×1.2 ≈ 万元/年」仅作直观参考。
（7-35k 直标后用户要求整体再压一档，故恢复 0.65 系数：35k 封顶落到难度 3。）
"""
from __future__ import annotations

# 市场档位对基准难度的偏置：大厂面试（算法/深挖）更狠 +1；创业少白板重广度 -1；
# 外企/中厂/不限 0（薪资已反映层级，避免双重计数）。
TIER_BIAS: dict[str, int] = {
    "大厂": 1,
    "外企": 0,
    "中厂": 0,
    "创业": -1,
    "不限": 0,
}

# 角色薪资相对偏移（千/月）：高薪岗同薪资=更初级（负偏移），低薪岗同薪资=更资深（正偏移）。
# 以「后端/普通开发」为参考(0)，偏移值依据 CSDN MCP 社区 2026 年报分岗位薪资中心差估算（v1，可调）。
# 算法/AI/大模型 同薪约低 1 档、数据次之；测试/运维 同薪约高 1 档。
ROLE_PAY_OFFSET: dict[str, int] = {
    "算法": -8, "AI": -8, "大模型": -8, "数据": -4,
    "后端": 0, "前端": 1, "客户端": 2, "运维": 3, "SRE": 3,
    "测试": 6, "QA": 6,
}

# 薪资档位按 7-35k/月 分档 1-5 后，整体 ×0.65 再下调一档（用户 2026-09-17 要求整体再压一档）。
DIFFICULTY_SCALE = 0.65

# 行情关键词：识别偏冷 / 偏热，用于方向提示
_DEFENSE_KEYWORDS = ("收缩", "寒冬", "裁员", "下行", "降温", "分化", "hc少", "hc 少", "低迷")
_BOOM_KEYWORDS = ("火热", "扩张", "增长", "上行", "回暖", "红利", "缺人", "扩招", "AI")


# 薪资单位换算（仅用于展示）：千/月 → 万元/年。1 万元 = 10 千；12 薪近似。
_MONTHS_PER_YEAR = 12
_K_PER_W = 10


def _to_annual_w(monthly_k: float) -> float:
    """千/月 → 万元/年（12 薪近似）。25k/月 → 30w/年。"""
    return monthly_k * _MONTHS_PER_YEAR / _K_PER_W


def _salary_mid(lower: int, upper: int) -> float:
    """月薪(k)带中点，用于分档。"""
    if upper and upper > lower:
        return (lower + upper) / 2
    return float(lower)


def _band(mid_k: float) -> int:
    """月薪(k)中点 → 经验层级档位 1-5（区间 7k 起步 ~ 35k 封顶）。

    分档：<12k 实习/入门；12-18k 初级；18-25k 中级；25-30k 高级；≥30k 专家/架构。
    """
    if mid_k < 12:
        return 1
    if mid_k < 18:
        return 2
    if mid_k < 25:
        return 3
    if mid_k < 30:
        return 4
    return 5


def salary_to_baseline(lower: int, upper: int, tier: str = "不限", role: str = "后端") -> int:
    """薪资带（千/月）× 市场档位 × 技术岗 → 基准难度档位 1-5（确定性映射）。

    先按角色薪资偏移折算「等效月薪中点」(mid + ROLE_PAY_OFFSET)，再用 _band 分档（1-5），
    整体 ×DIFFICULTY_SCALE 四舍五入下调，最后叠加档位偏置，clamp 到 1-5。
    未匹配角色按参考岗(后端, 偏移 0) 处理。
    """
    eff_mid = _salary_mid(lower, upper) + ROLE_PAY_OFFSET.get(role, 0)
    scaled = int(_band(eff_mid) * DIFFICULTY_SCALE + 0.5)
    biased = scaled + TIER_BIAS.get(tier, 0)
    return max(1, min(5, biased))


def next_difficulty(cur: int, score: int) -> tuple[int, str]:
    """会话内按评分动态调整难度与趋势：

    - 评分 >= 75：升级（难度+1），并切换方向
    - 评分 < 50：降级（难度-1），补基础
    - 其余：保持，追问关键细节
    """
    if score >= 75:
        return min(5, cur + 1), "升级/换方向"
    if score < 50:
        return max(1, cur - 1), "降级/补基础"
    return cur, "追问关键细节"


def direction_hint(
    lower: int,
    upper: int,
    tier: str,
    market_context: str,
    weaknesses: str,
    role: str,
    diff: int,
) -> str:
    """生成确定性「出题方向」提示，注入面试官 prompt。

    综合：薪资档位（按角色偏移折算后 7-35k/月 分档 ×0.65 再压一档）、市场档位、行情关键词、薄弱点、当前难度。
    level 标签直接由 salary_to_baseline 推导，与难度数字保持一致，避免双重标准。
    """
    base = salary_to_baseline(lower, upper, tier, role)
    level = {1: "实习/入门", 2: "初级", 3: "中级", 4: "高级", 5: "专家/架构"}.get(base, "初级")

    ann_lo = _to_annual_w(lower)
    ann_hi = _to_annual_w(upper) if upper else ann_lo
    parts: list[str] = [
        f"候选人目标为{level}岗（基准难度 {base}/5，薪资约{lower}-{upper}k/月 ≈ {ann_lo:.0f}-{ann_hi:.0f}w/年，市场档位{tier}）"
    ]

    if diff >= 4:
        parts.append("高难度档位：减少行为题，侧重系统设计/架构与原理深挖（technical 为主）")
    elif diff <= 2:
        parts.append("基础档位：以核心概念与基础编码题为主，先夯实再进阶")
    else:
        parts.append("中等难度：技术题与行为题均衡，关注实战落地")

    mc = market_context or ""
    if any(k in mc for k in _DEFENSE_KEYWORDS):
        parts.append("当前行情偏冷/分化：侧重稳定性、底层原理、性价比与抗压表达")
    if any(k in mc for k in _BOOM_KEYWORDS):
        parts.append("当前行情偏热/AI 主线：侧重业务落地、前沿技术与扩展开拓")

    if weaknesses and weaknesses.strip():
        parts.append(f"优先覆盖薄弱点：{weaknesses.strip()}")

    if role and role.strip():
        parts.append(f"围绕目标岗位「{role.strip()}」组织问题")

    return "；".join(parts)
