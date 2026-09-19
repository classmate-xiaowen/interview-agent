import re
from app.schemas.resume import PiiItem, MaskSelection

_PLACEHOLDER = {
    "name": "[姓名]", "phone": "[电话]", "email": "[邮箱]",
    "id_card": "[身份证]", "company": "[公司]", "address": "[住址]",
    "social": "[社交账号]",
}

_PATTERNS = {
    "phone": re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"),
    "email": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    "id_card": re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)"),
    "company": re.compile(r"[一-龥A-Za-z0-9]+?(?:公司|集团|科技|有限公司|股份公司|企业|银行|大学|学院|研究所|医院|工厂)"),
    "address": re.compile(r"[一-龥]{2,}(?:省|市|区|县|镇|路|街|道|号|栋|幢|单元|室|楼|大厦|广场|园区|巷)"),
    "social": re.compile(r"(?:微信|微信号|WeChat|QQ|qq|抖音|小红书|微博)[：:\s]*[A-Za-z0-9_-]{4,}"),
    "name": re.compile(r"(?:姓名|我叫|名字)[：:\s]*([一-龥]{2,4})|([一-龥]{2,3})(?:先生|女士|同学)"),
}


def detect_pii(text: str) -> list[PiiItem]:
    """确定性正则识别 7 类疑似 PII，去重叠后按起点升序返回。"""
    raw: list[PiiItem] = []
    for cat, pat in _PATTERNS.items():
        for m in pat.finditer(text):
            if cat == "name":
                val = m.group(1) or m.group(2)
                if not val:
                    continue
                start, end = (m.span(1) if m.group(1) else m.span(2))
            else:
                val = m.group(0)
                start, end = m.span(0)
            raw.append(PiiItem(category=cat, text=val, start=start, end=end))
    # 去重叠：长匹配优先（避免身份证被手机号/QQ 切碎），保留不重叠项
    raw.sort(key=lambda x: (-(x.end - x.start), x.start))
    accepted: list[PiiItem] = []
    for it in raw:
        if any(not (it.end <= a.start or it.start >= a.end) for a in accepted):
            continue
        accepted.append(it)
    accepted.sort(key=lambda x: x.start)
    return accepted


def apply_masks(text: str, selections: list[MaskSelection]) -> tuple[str, list[PiiItem]]:
    """按 selections 生成脱敏文本。mask=█ 块，placeholder=类型标签，ignore=跳过。
    从右往左替换以避免索引位移。"""
    accepted_sels = [s if isinstance(s, MaskSelection) else MaskSelection(**s) for s in selections]
    applied: list[PiiItem] = []
    ops = sorted(
        [s for s in accepted_sels if s.action != "ignore"],
        key=lambda s: s.start, reverse=True,
    )
    out = text
    for s in ops:
        if s.start < 0 or s.end > len(out) or s.start >= s.end:
            continue
        if s.action == "placeholder":
            repl = _PLACEHOLDER.get(s.category, "[PII]")
        else:  # mask
            repl = "█" * max(len(out[s.start:s.end]), 3)
        out = out[:s.start] + repl + out[s.end:]
        applied.append(PiiItem(
            category=s.category, text=repl,
            start=s.start, end=s.start + len(repl),
        ))
    applied.sort(key=lambda x: x.start)
    return out, applied
