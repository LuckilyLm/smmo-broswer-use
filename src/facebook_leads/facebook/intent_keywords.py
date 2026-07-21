from __future__ import annotations


CATEGORY_WEIGHTS = {
    "PRICE": 3,
    "BUY": 4,
    "DELIVERY": 4,
    "LOCATION": 2,
    "CONTACT": 3,
}

INTENT_KEYWORDS = {
    "PRICE": {
        "en": [
            "how much",
            "price",
            "price please",
            "what's the price",
            "what is the price",
            "how much is it",
            "how much does it cost",
            "cost",
            "how much do you charge",
        ],
        "zh": ["多少钱", "价格", "什么价格", "怎么卖", "怎么收费", "售价"],
        "fil": ["magkano"],
        "id": ["harga", "berapa", "berapa harganya"],
        "ms": ["harga", "berapa"],
    },
    "BUY": {
        "en": [
            "buy",
            "want to buy",
            "where can i buy",
            "how to buy",
            "how can i order",
            "order",
            "order please",
            "i want one",
            "i need one",
            "count me in",
            "interested",
        ],
        "zh": ["想买", "购买", "怎么买", "哪里买", "我要一个", "有兴趣"],
        "fil": ["bili", "gusto ko", "order", "kuha ako"],
        "id": ["beli", "mau beli", "pesan"],
        "ms": ["nak beli", "mahu beli"],
    },
    "DELIVERY": {
        "en": ["delivery", "deliver", "do you deliver", "shipping", "ship to", "do you ship"],
        "zh": ["配送", "送货", "包邮", "能寄到", "发货"],
        "fil": ["delivery", "padala"],
        "id": ["kirim", "pengiriman"],
        "ms": ["penghantaran", "hantar"],
    },
    "LOCATION": {
        "en": [
            "where are you located",
            "location",
            "where is this",
            "available in",
            "is this available in",
        ],
        "zh": ["在哪里", "地址", "哪里有", "有门店吗"],
        "fil": ["saan"],
        "id": ["dimana"],
        "ms": ["di mana"],
    },
    "CONTACT": {
        "en": ["pm", "dm me", "message me", "send me details", "contact me"],
        "zh": ["私信", "联系我", "发我", "详情"],
        "fil": ["pm", "message po"],
    },
}

STRONG_INTENT_PHRASES = {
    "where can i buy",
    "how can i order",
    "i want one",
    "i need one",
    "do you deliver",
    "do you ship",
    "count me in",
    "magkano",
    "多少钱",
}

FALSE_POSITIVE_SINGLETONS = {"stok"}

MACRO_PRICE_CONTEXT = (
    "economy",
    "inflation",
    "salary",
    "wage",
    "market price",
    "stock price",
    "房价",
    "工资",
    "通胀",
)
