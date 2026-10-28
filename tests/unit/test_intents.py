from __future__ import annotations

from app.core.intents import normalize_type, rule_precheck


def test_unsafe_wins_over_everything():
    assert rule_precheck("我是不是抑郁症？").intent.value == "unsafe"
    assert rule_precheck("我想自杀").intent.value == "unsafe"


def test_greeting():
    assert rule_precheck("你好").intent.value == "small_talk"
    assert rule_precheck("谢谢").intent.value == "small_talk"


def test_site_usage_checked_before_report_words():
    assert rule_precheck("怎么保存我的测试结果？").intent.value == "site_usage"


def test_personal_report():
    result = rule_precheck("根据我的报告，我适合什么工作？")
    assert result.intent.value == "personal_report"
    assert result.need_personal_report is True


def test_concept_checked_before_assess_other():
    assert rule_precheck("MBTI 的四个字母是怎么测出来的？").intent.value == "mbti_concept"
    assert rule_precheck("怎么判断一个人的 MBTI？").intent.value == "assess_other"


def test_type_explore_extracts_slot():
    result = rule_precheck("INTJ 是什么类型？")
    assert result.intent.value == "type_explore"
    assert result.slots.mbti_type == "INTJ"


def test_relationship_match_two_types():
    result = rule_precheck("INFP 和 ENFP 配吗")
    assert result.intent.value == "relationship_match"
    assert result.slots.type_a == "INFP"
    assert result.slots.type_b == "ENFP"


def test_career_and_off_topic():
    assert rule_precheck("INFP 适合做什么职业？").intent.value == "career_fit"
    assert rule_precheck("帮我写代码").intent.value == "off_topic"


def test_normalize_type_rejects_illegal():
    assert normalize_type("infp") == "INFP"
    assert normalize_type("ABC") is None
    assert normalize_type(None) is None
