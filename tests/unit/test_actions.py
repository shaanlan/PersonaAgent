from __future__ import annotations

from app.agent.actions import build_actions, valid_url
from app.schemas.intent import Slots


def test_url_whitelist_rejects_dangerous():
    assert not valid_url("javascript:alert(1)")
    assert not valid_url("//evil.com/x")
    assert not valid_url("https://evil.com/x")
    assert not valid_url("/zh-CN/../etc/passwd")
    assert not valid_url("/zh-CN/type/INFP")  # uppercase slug not allowed
    assert not valid_url("/fr/type/intj")  # unknown locale


def test_url_whitelist_accepts_site_paths():
    assert valid_url("/zh-CN/type/intj")
    assert valid_url("/en/career")
    assert valid_url("/pt-BR/account/reports")


def test_build_actions_type_explore_uses_lowercase_url():
    actions = build_actions("type_explore", Slots(mbti_type="INTJ"), "zh-CN", None)
    assert [a.url for a in actions] == ["/zh-CN/type/intj", "/zh-CN/relationship"]
    assert "INTJ" in actions[0].label  # label keeps display casing
    assert actions[0].priority == "primary"


def test_build_actions_max_two():
    actions = build_actions("career_fit", Slots(mbti_type="INFP"), "zh-CN", None)
    assert len(actions) <= 2


def test_build_actions_personal_report_switches_on_report():
    without = build_actions("personal_report", Slots(), "zh-CN", None)
    assert without[0].url == "/zh-CN/quiz"
    with_report = build_actions("personal_report", Slots(), "zh-CN", {"result_type": "INFP"})
    assert with_report[0].url == "/zh-CN/account/reports"


def test_build_actions_localized_labels():
    actions = build_actions("career_fit", Slots(), "ja", None)
    assert actions[0].label == "MBTI キャリアガイドを見る"


def test_unsafe_has_no_actions():
    assert build_actions("unsafe", Slots(), "zh-CN", None) == []
    assert build_actions("off_topic", Slots(), "zh-CN", None) == []
