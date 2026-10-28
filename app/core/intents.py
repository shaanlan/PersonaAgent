from __future__ import annotations

import re

from app.schemas.intent import Intent, RouteResult, Slots

TYPE_RE = re.compile(r"\b([EI][NS][TF][JP])\b", re.I)

UNSAFE_WORDS = ["自杀", "自残", "想死", "不想活", "暴力", "杀人", "诊断", "抑郁症", "suicide", "self-harm"]
GREETING_WORDS = ["你好", "您好", "谢谢", "在吗", "hello", "hi", "hey", "thanks"]

_TYPE_WORDS = ["type_explore", "性格", "是什么类型", "是什么样的人"]
_SELF_WORDS = ["我是", "自己", "真的", "自测", "测试"]
_OTHER_WORDS = ["怎么判断", "怎么测", "判断一个人", "测别人", "女朋友", "男朋友", "同事", "领导", "他人", "别人"]
_MATCH_WORDS = ["配不配", "配吗", "合适吗", "双人", "和他配", "和她配"]
_CAREER_WORDS = ["职业", "工作", "就业", "上班", "职场"]
_RELATION_WORDS = ["恋爱", "婚姻", "朋友", "相处", "关系", "伴侣"]
_CONCEPT_WORDS = ["四个字母", "理论", "原理", "怎么测出来", "科学"]
_REPORT_WORDS = ["我的报告", "根据我", "我最近测试", "我的测试结果"]
_SITE_WORDS = ["登录", "账号", "保存", "隐私", "怎么用"]


def rule_precheck(text: str) -> RouteResult:
    """Low-cost rule precheck (design §6.2.1). Candidates only; LLM result wins when valid,
    safety rules always win.
    """
    t = text.lower()
    types = [m.upper() for m in TYPE_RE.findall(text)]

    if any(w in t for w in UNSAFE_WORDS):
        return RouteResult(intent=Intent.UNSAFE, confidence=0.95, search_query=text)
    if any(w in t for w in GREETING_WORDS) and len(t) <= 12:
        return RouteResult(intent=Intent.SMALL_TALK, confidence=0.9, search_query=text)

    intent = Intent.OFF_TOPIC
    confidence = 0.3
    # Site-operation words are the most specific "how do I use the site" signal and
    # must be checked before report words ("怎么保存我的测试结果" is site_usage, not a report ask).
    if any(w in t for w in _SITE_WORDS):
        intent, confidence = Intent.SITE_USAGE, 0.78
    elif any(w in t for w in _REPORT_WORDS):
        intent, confidence = Intent.PERSONAL_REPORT, 0.9
    elif any(w in t for w in _MATCH_WORDS):
        intent, confidence = Intent.RELATIONSHIP_MATCH, 0.82
    elif any(w in t for w in _CONCEPT_WORDS):
        intent, confidence = Intent.MBTI_CONCEPT, 0.8
    elif any(w in t for w in _OTHER_WORDS):
        intent, confidence = Intent.ASSESS_OTHER, 0.82
    elif any(w in t for w in _CAREER_WORDS):
        intent, confidence = Intent.CAREER_FIT, 0.86
    elif any(w in t for w in _RELATION_WORDS):
        intent, confidence = Intent.RELATIONSHIP_CONTENT, 0.8
    elif any(w in t for w in _SELF_WORDS):
        intent, confidence = Intent.SELF_ASSESS, 0.72
    elif types:
        intent, confidence = Intent.TYPE_EXPLORE, 0.85
    elif "mbti" in t:
        intent, confidence = Intent.MBTI_CONCEPT, 0.62

    slots = extract_slots(text, intent)
    search_query = text if not slots.mbti_type else f"{text} {slots.mbti_type}"
    need_report = intent == Intent.PERSONAL_REPORT
    clarify = None
    if confidence < 0.45:
        clarify = "我还不确定你想问哪方面，可以补充一下具体场景吗？"
    return RouteResult(
        intent=intent,
        confidence=confidence,
        slots=slots,
        search_query=search_query,
        need_personal_report=need_report,
        clarify_question=clarify,
    )


def extract_slots(text: str, intent: Intent | str) -> Slots:
    types = [m.upper() for m in TYPE_RE.findall(text)]
    slots = Slots()
    if intent == Intent.RELATIONSHIP_MATCH or intent == "relationship_match":
        if types:
            slots.type_a = types[0]
        if len(types) > 1:
            slots.type_b = types[1]
    elif types:
        slots.mbti_type = types[0]
    role_map = {
        "女朋友": "partner",
        "男朋友": "partner",
        "伴侣": "partner",
        "朋友": "friend",
        "同事": "colleague",
        "领导": "boss",
    }
    for word, role in role_map.items():
        if word in text:
            slots.target_role = role  # type: ignore[assignment]
            break
    return slots


def normalize_type(value: str | None) -> str | None:
    if not value:
        return None
    candidate = value.strip().upper()
    return candidate if TYPE_RE.fullmatch(candidate) else None
