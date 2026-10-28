from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class Intent(StrEnum):
    TYPE_EXPLORE = "type_explore"
    SELF_ASSESS = "self_assess"
    ASSESS_OTHER = "assess_other"
    RELATIONSHIP_MATCH = "relationship_match"
    CAREER_FIT = "career_fit"
    RELATIONSHIP_CONTENT = "relationship_content"
    MBTI_CONCEPT = "mbti_concept"
    PERSONAL_REPORT = "personal_report"
    SITE_USAGE = "site_usage"
    SMALL_TALK = "small_talk"
    OFF_TOPIC = "off_topic"
    UNSAFE = "unsafe"


class Slots(BaseModel):
    mbti_type: str | None = None
    type_a: str | None = None
    type_b: str | None = None
    target_role: Literal["partner", "friend", "colleague", "boss"] | None = None
    relation_type: str | None = None
    career_slug: str | None = None
    article_slug: str | None = None


class RouteResult(BaseModel):
    intent: Intent
    confidence: float = Field(ge=0.0, le=1.0)
    slots: Slots = Field(default_factory=Slots)
    search_query: str = ""
    need_personal_report: bool = False
    clarify_question: str | None = None


class Action(BaseModel):
    type: Literal["navigate", "start_test", "open_report", "open_history"] = "navigate"
    label: str
    description: str | None = None
    url: str
    priority: Literal["primary", "secondary"] = "primary"
    icon: str | None = None


class Source(BaseModel):
    id: str
    title: str
    section: str | None = None
    url: str
    source_type: str | None = None
    score: float | None = None
