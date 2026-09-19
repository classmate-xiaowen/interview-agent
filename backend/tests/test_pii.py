import pytest
from app.services import pii


def test_detect_phone():
    items = pii.detect_pii("我的手机号是13812345678，请联系。")
    phones = [i for i in items if i.category == "phone"]
    assert phones and phones[0].text == "13812345678"


def test_detect_email():
    items = pii.detect_pii("邮箱: jane.doe@example.com 谢谢")
    emails = [i for i in items if i.category == "email"]
    assert emails and "@" in emails[0].text


def test_detect_id_card():
    items = pii.detect_pii("身份证11010519900307123X结尾")
    ids = [i for i in items if i.category == "id_card"]
    assert ids and len(ids[0].text) in (18, 15)


def test_detect_company():
    items = pii.detect_pii("曾就职于字节跳动科技有限公司")
    comp = [i for i in items if i.category == "company"]
    assert comp and "字节" in comp[0].text


def test_detect_address():
    items = pii.detect_pii("住址：北京市海淀区中关村南大街5号")
    addr = [i for i in items if i.category == "address"]
    assert addr


def test_detect_social():
    items = pii.detect_pii("微信: my_wechat_01 联系")
    soc = [i for i in items if i.category == "social"]
    assert soc and "my_wechat_01" in soc[0].text


def test_detect_name_heuristic():
    items = pii.detect_pii("我叫张三，今年28岁")
    names = [i for i in items if i.category == "name"]
    assert names and "张三" in names[0].text


def test_overlap_dedup():
    items = pii.detect_pii("身份证11010519900307123X")
    cats = [i.category for i in items]
    assert "phone" not in cats


def test_apply_masks_placeholder():
    text = "手机13812345678联系"
    sels = [{"start": 2, "end": 13, "category": "phone", "action": "placeholder"}]
    out, applied = pii.apply_masks(text, sels)
    assert "[电话]" in out and "13812345678" not in out
    assert len(applied) == 1


def test_apply_masks_mask():
    text = "手机13812345678联系"
    sels = [{"start": 2, "end": 13, "category": "phone", "action": "mask"}]
    out, _ = pii.apply_masks(text, sels)
    assert "█" in out and "13812345678" not in out


def test_apply_masks_ignore():
    text = "手机13812345678联系"
    sels = [{"start": 2, "end": 13, "category": "phone", "action": "ignore"}]
    out, applied = pii.apply_masks(text, sels)
    assert "13812345678" in out and applied == []
