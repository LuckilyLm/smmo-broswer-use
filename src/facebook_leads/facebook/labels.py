from __future__ import annotations


CONTENT_TYPE_LABELS = {
    "reel": "短视频",
    "post": "帖子",
    "video": "视频",
    "unknown": "未知内容",
    None: "未知内容",
}

INTENT_LEVEL_LABELS = {
    "high": "高意向",
    "medium": "中等意向",
    "low": "低意向",
    "none": "无意向",
}

INTENT_CATEGORY_LABELS = {
    "PRICE": "价格咨询",
    "BUY": "购买意向",
    "DELIVERY": "配送咨询",
    "LOCATION": "地区 / 门店咨询",
    "CONTACT": "联系意向",
}


def content_type_label(value: str | None) -> str:
    return CONTENT_TYPE_LABELS.get(value, CONTENT_TYPE_LABELS[None])


def intent_level_label(value: str | None) -> str:
    return INTENT_LEVEL_LABELS.get(value or "none", INTENT_LEVEL_LABELS["none"])


def intent_category_label(value: str) -> str:
    return INTENT_CATEGORY_LABELS.get(value, value)
