from __future__ import annotations

import re
import unicodedata
from typing import Literal

from pydantic import BaseModel, Field, model_validator


IntentType = Literal["RELATION", "ATTRIBUTE", "INTRODUCTION", "UNSUPPORTED"]


class QaIntent(BaseModel):
    intent: IntentType
    subject: str = ""
    relation: str | None = None
    property: str | None = None
    confidence: float = Field(default=1.0, ge=0, le=1)

    @model_validator(mode="after")
    def validate_shape(self) -> QaIntent:
        if self.intent == "RELATION" and not self.relation:
            raise ValueError("relation is required for RELATION")
        if self.intent == "ATTRIBUTE" and not self.property:
            raise ValueError("property is required for ATTRIBUTE")
        if self.intent in {"RELATION", "ATTRIBUTE", "INTRODUCTION"} and not self.subject:
            raise ValueError("subject is required for supported intents")
        return self


_PREFIXES = ("请问", "请告诉我", "告诉我", "能否告诉我", "请帮我查一下")
_RELATION_MARKERS: tuple[tuple[str, str], ...] = (
    ("隶属于什么门派", "MEMBER_OF"),
    ("属于哪个门派", "MEMBER_OF"),
    ("属于什么门派", "MEMBER_OF"),
    ("加入了哪个门派", "MEMBER_OF"),
    ("拜入了哪个门派", "MEMBER_OF"),
    ("的师父", "MASTER_OF"),
    ("的師父", "MASTER_OF"),
    ("的师傅", "MASTER_OF"),
    ("的師傅", "MASTER_OF"),
    ("拜谁为师", "MASTER_OF"),
    ("掌握什么武功", "KNOWS"),
    ("会什么武功", "KNOWS"),
    ("会哪些武功", "KNOWS"),
    ("的敌人", "ENEMY_OF"),
    ("的對手", "ENEMY_OF"),
    ("的对手", "ENEMY_OF"),
    ("的盟友", "ALLY_OF"),
    ("的朋友", "ALLY_OF"),
    ("持有什么", "HOLDS"),
    ("拥有何物", "HOLDS"),
    ("发生在哪里", "OCCURS_AT"),
)
_ATTRIBUTE_MARKERS: tuple[tuple[str, str], ...] = (
    ("的性别", "gender"),
    ("性别", "gender"),
    ("的身份", "identity"),
    ("是什么身份", "identity"),
    ("的称号", "honorific"),
    ("的尊称", "honorific"),
    ("的外号", "honorific"),
    ("有哪些称号", "honorific"),
    ("的生死", "life_status"),
    ("是否在世", "life_status"),
    ("的活动区域", "activity_region"),
    ("的所在区域", "region"),
    ("的特征", "characteristic"),
    ("的特点", "characteristic"),
)


def normalize_question(question: str) -> str:
    text = unicodedata.normalize("NFKC", question).strip()
    text = re.sub(r"\s+", "", text).rstrip("？?。！!；;")
    for prefix in sorted(_PREFIXES, key=len, reverse=True):
        if text.startswith(prefix):
            text = text[len(prefix) :]
            break
    return text


def extract_subject(question: str, markers: tuple[str, ...]) -> str | None:
    for marker in sorted(markers, key=len, reverse=True):
        position = question.find(marker)
        if position > 0:
            subject = question[:position].strip(" ，,：:")
            return subject or None
    return None


def parse_local_intent(question: str) -> QaIntent | None:
    text = normalize_question(question)
    if not text:
        return None

    for marker, relation in _RELATION_MARKERS:
        if marker in text:
            subject = extract_subject(text, (marker,))
            if subject:
                return QaIntent(intent="RELATION", subject=subject, relation=relation)

    for marker, property_id in _ATTRIBUTE_MARKERS:
        if marker in text:
            subject = extract_subject(text, (marker,))
            if subject:
                return QaIntent(intent="ATTRIBUTE", subject=subject, property=property_id)

    if text.endswith("是谁"):
        subject = text[: -len("是谁")].rstrip("的")
        if subject:
            return QaIntent(intent="INTRODUCTION", subject=subject)
    return None
