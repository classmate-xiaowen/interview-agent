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


# ---------------------------------------------------------------------------
# 评分校准层（确定性、可单测、单调）
#
# 设计原则：与出题难度档(1-5)绑定，把 LLM 原始分「重定标」到统一的难度区间。
# 目的是【一致性 / 防漂移】——让分数跨模型、跨提示词、跨时间【可比且稳定】，
# 而【不是】让分数"更准确"。LLM 原始分的排序误差与噪声会被单调映射原样继承，
# 校准层不修正这些（绝对准确度需靠更好的 rubric / 参考锚定 / 人工标注，见 eval 设计）。
# 数值分经 calibrate_score 软拉+clamp（消除系统性刻度漂移、跨模型一致）；
# 5 级定性结论 score_to_level 由校准后分数确定性推导（不直接信模型的文字判断）。
# 数据来源：xtechtools《中国大厂技术面试 2026 全攻略》合格线 + 脉脉 5 维评分框架
#          （用于设定区间梯度，使"达标"在各难度档含义一致、可横向比较，而非判定绝对真实水平）。
# ---------------------------------------------------------------------------
from typing import Literal

OverallLevel = Literal["优秀", "良好", "合格", "待提升", "不合格"]

# 国内大厂"达标回答"目标区间 (floor, ceil) 与及格线 (gate)，按难度档分级校准。
# 关键：级别越高，"达标分"越低——资深岗需难题+系统+深挖才合格，而非每题满分。
SCORE_BAND: dict[int, tuple[int, int, int]] = {
    1: (78, 90, 55),  # 实习/入门
    2: (72, 85, 55),  # 初级
    3: (65, 80, 50),  # 中级
    4: (58, 72, 50),  # 高级
    5: (52, 65, 50),  # 专家/架构
}

_LEVEL_LABEL = {1: "实习/入门", 2: "初级", 3: "中级", 4: "高级", 5: "专家/架构"}


def difficulty_from_years(years: int | None) -> int:
    """把候选人工作年限映射到难度档 1-5（校招/初级≈2-3，资深≈4-5）。"""
    if not years or years < 1:
        return 1
    if years < 3:
        return 2
    if years < 5:
        return 3
    if years < 8:
        return 4
    return 5


def _company_weight(company: str) -> str:
    """按目标公司微调评分维度权重（国内厂风差异）。"""
    c = (company or "").lower()
    if "字节" in c or "bytedance" in c or "douyin" in c:
        return "该厂偏重算法与代码能力"
    if "阿里" in c or "alibaba" in c:
        return "该厂偏重项目深挖与沟通表达"
    if "腾讯" in c or "tencent" in c:
        return "该厂偏重工程素养与代码质量"
    if "美团" in c or "meituan" in c:
        return "该厂偏重业务落地与成本治理"
    return ""


def score_calibration(diff: int, company: str = "") -> str:
    """生成注入 EVAL 提示的中文评分区间句（统一区间 + 厂风权重，使模型原始分落在合理范围、缩小与校准后的差距）。"""
    floor, ceil, _ = SCORE_BAND.get(diff, SCORE_BAND[3])
    level = _LEVEL_LABEL.get(diff, "中级")
    parts = [
        f"本题对标{level}难度（国内大厂合格线）：清晰、正确、切中要害的回答即应得 {floor}-{ceil} 分，"
        f"勿因回答简短而压分——面试作答本就简短，简洁且答到点上即达标。",
        "仅当出现事实性错误、明显跑题或完全无思路时才低于及格线。",
        "八股文式只背概念不讲清 trade-off 会扣分；能结合场景讲清取舍才得分。",
    ]
    w = _company_weight(company)
    if w:
        parts.append(w + "，评分时可对该维度适当加权。")
    return "".join(parts)


def calibrate_score(raw: int, diff: int) -> int:
    """把 LLM 原始分单调重定标到该难度档统一区间并 clamp（一致性/防漂移，非"更准确"）。

    ⚠️ 本函数不做绝对准确度修正：只消除 LLM 的系统性刻度漂移（跨模型/提示词/时间的整体平移），
    并保留 LLM 的排序判断与相对区分。原始分本身的排序错误与噪声会被单调映射原样继承。

    - 原始分低于及格线：认定为确实不足，不强行拉入合格区（设 30 分下限避免过苛）。
    - 原始分在合格线及以上：向区间中点软拉 60%，再 clamp 到 [floor, ceil]，
      使不同难度档的"达标"落在各自统一区间内（可比），并避免分数被无意义顶到 95+。
    """
    raw = max(0, min(100, int(raw)))
    floor, ceil, gate = SCORE_BAND.get(diff, SCORE_BAND[3])
    if raw < gate:
        return max(raw, 30)
    center = (floor + ceil) / 2
    pulled = raw + (center - raw) * 0.6
    return int(max(floor, min(ceil, round(pulled))))


def score_to_level(raw: int, diff: int) -> OverallLevel:
    """由校准后分数映射国内 5 级定性结论（与难度档绑定，分级呈现）。"""
    floor, ceil, gate = SCORE_BAND.get(diff, SCORE_BAND[3])
    center = (floor + ceil) / 2
    if raw >= ceil:
        return "优秀"
    if raw >= center:
        return "良好"
    if raw >= floor:
        return "合格"
    if raw >= gate:
        return "待提升"
    return "不合格"


# ---------------------------------------------------------------------------
# 维度拆分聚合（A2：比模型整体给一个数更可靠）
#
# LLM 对"逐维评分"比"整体给一个数"更稳（减少光环效应）。故 EVAL 让模型先给 5 维分项分，
# 再由本确定性纯函数加权聚合成单一原始分；之后照常走 calibrate_score 校准。
# 缺失维度不参与加权（权重归一化到已有维度），避免无谓拉低总分。
# ---------------------------------------------------------------------------
EVAL_DIMENSIONS: dict[str, str] = {
    "boundary": "问题拆解与边界确认",
    "depth": "技术理解深度（真懂还是套方案/背八股，能结合场景讲清 trade-off 才得分）",
    "expression": "编码/表达质量（讲清思路即达标，简短但切中要害不扣分）",
    "communication": "沟通与协作感",
    "mindset": "心智与团队匹配",
}

DIMENSION_WEIGHTS: dict[str, float] = {
    "boundary": 0.20,
    "depth": 0.30,       # 技术岗最核心：理解深度权重最高
    "expression": 0.20,
    "communication": 0.15,
    "mindset": 0.15,
}


def aggregate_dimensions(dims: dict[str, int] | None) -> int | None:
    """把 LLM 的 5 维分项分加权聚合成单一原始分（确定性纯函数，不做校准）。

    - dims 为 None 或全缺失 → 返回 None（调用方应退回模型整体分）。
    - 维度值裁剪到 [0,100]；缺失维度权重归一化到其余维度，避免惩罚。
    """
    if not dims:
        return None
    acc = 0.0
    total_w = 0.0
    for k, w in DIMENSION_WEIGHTS.items():
        v = dims.get(k)
        if v is None:
            continue
        acc += max(0, min(100, int(v))) * w
        total_w += w
    if total_w == 0:
        return None
    return int(round(acc / total_w))
