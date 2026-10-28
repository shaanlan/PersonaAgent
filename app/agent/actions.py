from __future__ import annotations

import re
from typing import Any

from app.schemas.intent import Action, Slots

ROUTE_CATALOG: dict[str, dict[str, Any]] = {
    "self_quiz": {"path": "/{lang}/quiz", "page_type": "quiz"},
    "third_person_quiz": {"path": "/{lang}/third-person/quiz", "page_type": "third_person"},
    "dual_test": {"path": "/{lang}/dual-test", "page_type": "dual_test"},
    "type_detail": {"path": "/{lang}/type/{type}", "page_type": "type_detail"},
    "career_index": {"path": "/{lang}/career", "page_type": "career_index"},
    "career_detail": {"path": "/{lang}/career/{slug}", "page_type": "career_detail"},
    "relationship_index": {"path": "/{lang}/relationship", "page_type": "relationship_index"},
    "relationship_detail": {"path": "/{lang}/relationship/{slug}", "page_type": "relationship_detail"},
    "blog_index": {"path": "/{lang}/blog", "page_type": "blog_index"},
    "blog_detail": {"path": "/{lang}/blog/{slug}", "page_type": "blog_detail"},
    "account": {"path": "/{lang}/account", "page_type": "account"},
    "account_reports": {"path": "/{lang}/account/reports", "page_type": "account_reports"},
    "about": {"path": "/{lang}/about", "page_type": "about"},
}

LABELS: dict[str, dict[str, str]] = {
    "self_quiz": {
        "zh-CN": "开始 MBTI 自测",
        "en": "Take the MBTI test",
        "ja": "MBTI テストを始める",
        "ko": "MBTI 테스트 시작하기",
        "es": "Hacer el test de MBTI",
        "pt-BR": "Fazer o teste de MBTI",
    },
    "third_person_quiz": {
        "zh-CN": "用第三人称测试观察他人",
        "en": "Observe others with the third-person test",
        "ja": "第三者テストで相手を観察する",
        "ko": "3인칭 테스트로 관찰하기",
        "es": "Observar a otros con el test de terceros",
        "pt-BR": "Observar outros com o teste de terceiros",
    },
    "dual_test": {
        "zh-CN": "做双人关系测试",
        "en": "Take the couple test",
        "ja": "カップルテストを受ける",
        "ko": "커플 테스트 시작하기",
        "es": "Hacer la prueba de pareja",
        "pt-BR": "Fazer o teste de casal",
    },
    "type_detail": {
        "zh-CN": "查看 {type} 类型详情",
        "en": "View {type} type details",
        "ja": "{type} の詳細を見る",
        "ko": "{type} 유형 상세 보기",
        "es": "Ver detalles del tipo {type}",
        "pt-BR": "Ver detalhes do tipo {type}",
    },
    "career_index": {
        "zh-CN": "查看 MBTI 职业指南",
        "en": "Open the MBTI career guide",
        "ja": "MBTI キャリアガイドを見る",
        "ko": "MBTI 커리어 가이드 보기",
        "es": "Ver la guía de carreras MBTI",
        "pt-BR": "Ver o guia de carreiras MBTI",
    },
    "relationship_index": {
        "zh-CN": "查看关系相处指南",
        "en": "Open the relationship guide",
        "ja": "関係のガイドを見る",
        "ko": "관계 가이드 보기",
        "es": "Ver la guía de relaciones",
        "pt-BR": "Ver o guia de relacionamentos",
    },
    "blog_index": {
        "zh-CN": "阅读 MBTI 概念文章",
        "en": "Read MBTI articles",
        "ja": "MBTI の記事を読む",
        "ko": "MBTI 글 읽기",
        "es": "Leer artículos de MBTI",
        "pt-BR": "Ler artigos de MBTI",
    },
    "account_reports": {
        "zh-CN": "查看我的测试报告",
        "en": "Open my reports",
        "ja": "自分のレポートを見る",
        "ko": "내 리포트 보기",
        "es": "Ver mis informes",
        "pt-BR": "Ver meus relatórios",
    },
    "about": {
        "zh-CN": "了解站点与账号说明",
        "en": "About this site and accounts",
        "ja": "サイトとアカウントについて",
        "ko": "사이트 및 계정 안내",
        "es": "Acerca del sitio y las cuentas",
        "pt-BR": "Sobre o site e as contas",
    },
}

_VALID_URL_RE = re.compile(r"^/(zh-CN|en|ja|ko|es|pt-BR)/[a-z0-9/_-]+$")


def valid_url(url: str) -> bool:
    """Server-side URL whitelist check (design §6.5.2)."""
    if not url.startswith("/") or url.startswith("//"):
        return False
    if "://" in url or ".." in url or "javascript:" in url.lower():
        return False
    return _VALID_URL_RE.match(url) is not None


def build_actions(
    intent: str,
    slots: Slots | dict[str, Any],
    lang: str,
    personal_report: dict[str, Any] | None,
) -> list[Action]:
    """Pure function building whitelisted actions (design §5.5.4/§6.3)."""
    if isinstance(slots, dict):
        slots = Slots(**{k: v for k, v in slots.items() if k in Slots.model_fields})
    mbti = slots.mbti_type or (personal_report or {}).get("result_type")
    plan: list[tuple[str, str, dict[str, str]]] = []
    if intent == "type_explore" and mbti:
        plan = [("type_detail", "primary", {"type": mbti}), ("relationship_index", "secondary", {})]
    elif intent == "self_assess":
        plan = [("self_quiz", "primary", {}), ("type_detail", "secondary", {"type": mbti or "infp"})]
    elif intent == "assess_other":
        plan = [("third_person_quiz", "primary", {}), ("type_detail", "secondary", {"type": mbti or "infj"})]
    elif intent == "relationship_match":
        plan = [("dual_test", "primary", {}), ("relationship_index", "secondary", {})]
    elif intent == "career_fit":
        plan = [("career_index", "primary", {}), ("type_detail", "secondary", {"type": mbti or "infp"})]
    elif intent == "relationship_content":
        plan = [("relationship_index", "primary", {}), ("type_detail", "secondary", {"type": mbti or "infp"})]
    elif intent == "mbti_concept":
        plan = [("blog_index", "primary", {}), ("self_quiz", "secondary", {})]
    elif intent == "personal_report":
        primary = "account_reports" if personal_report else "self_quiz"
        plan = [(primary, "primary", {}), ("career_index", "secondary", {})]
    elif intent == "site_usage":
        plan = [("about", "primary", {}), ("account_reports", "secondary", {})]

    actions: list[Action] = []
    for key, priority, params in plan:
        route = ROUTE_CATALOG.get(key)
        labels = LABELS.get(key)
        if not route or not labels:
            continue
        lower_params = {k: (v.lower() if isinstance(v, str) else v) for k, v in params.items()}
        path = route["path"].format(lang=lang, **lower_params)
        if not valid_url(path):
            continue
        label = labels.get(lang, labels["en"]).format(**params)
        actions.append(
            Action(
                type="start_test" if key in {"self_quiz", "third_person_quiz", "dual_test"} else "navigate",
                label=label,
                description=path,
                url=path,
                priority=priority,  # type: ignore[arg-type]
                icon=key,
            )
        )
    return actions[:2]
