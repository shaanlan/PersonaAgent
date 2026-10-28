from __future__ import annotations

SUPPORTED_LOCALES = ("zh-CN", "en", "ja", "ko", "es", "pt-BR")
DEFAULT_LOCALE = "zh-CN"

_LOCALE_ALIASES = {
    "zh": "zh-CN",
    "zh-cn": "zh-CN",
    "zh-hans": "zh-CN",
    "en": "en",
    "en-us": "en",
    "en-gb": "en",
    "ja": "ja",
    "ja-jp": "ja",
    "ko": "ko",
    "ko-kr": "ko",
    "es": "es",
    "es-es": "es",
    "pt": "pt-BR",
    "pt-br": "pt-BR",
    "pt-pt": "pt-BR",
}

SUGGESTED_QUESTIONS: dict[str, list[str]] = {
    "zh-CN": [
        "INTJ 是什么样的人？",
        "INFP 适合做什么职业？",
        "怎么判断同事的 MBTI？",
    ],
    "en": [
        "What is INTJ like?",
        "What careers fit INFP?",
        "How can I type a coworker?",
    ],
    "ja": ["INTJ とはどんな人？", "INFP に合う仕事は？", "同僚の MBTI はどう分かる？"],
    "ko": ["INTJ 는 어떤 사람인가요?", "INFP 에게 맞는 직업은?", "동료의 MBTI 는 어떻게 알 수 있나요?"],
    "es": ["¿Qué persona es INTJ?", "¿Qué carreras encajan con INFP?", "¿Cómo saber el MBTI de un compañero?"],
    "pt-BR": ["Qual é a pessoa INTJ?", "Que carreiras combinam com INFP?", "Como descobrir o MBTI de um colega?"],
}


def normalize_locale(locale: str | None) -> str:
    if not locale:
        return DEFAULT_LOCALE
    raw = locale.strip()
    if raw in SUPPORTED_LOCALES:
        return raw
    mapped = _LOCALE_ALIASES.get(raw.lower())
    if mapped:
        return mapped
    return DEFAULT_LOCALE


def suggested_questions(locale: str, limit: int = 3) -> list[str]:
    return SUGGESTED_QUESTIONS.get(normalize_locale(locale), SUGGESTED_QUESTIONS[DEFAULT_LOCALE])[:limit]
