from typing import Any

from app.qa.models import (
    QaRepresentativeEntity,
    QaSuggestion,
    QaSuggestionsResponse,
)


RELATION_QUESTIONS = (
    ("MASTER_OF", "{name}的师父是谁？"),
    ("MEMBER_OF", "{name}属于哪个门派？"),
    ("KNOWS", "{name}掌握什么武功？"),
)

ATTRIBUTE_QUESTIONS = (
    ("gender", "{name}的性别是什么？"),
    ("identity", "{name}是什么身份？"),
    ("honorific", "{name}有哪些称号？"),
    ("life_status", "{name}是否在世？"),
    ("activity_region", "{name}的活动区域在哪里？"),
    ("region", "{name}的所在区域是哪里？"),
    ("characteristic", "{name}有什么特点？"),
)


class QaSuggestionService:
    def __init__(self, repository: Any) -> None:
        self.repository = repository

    def suggest(self, project_id: str, project_title: str) -> QaSuggestionsResponse:
        candidate = self.repository.qa_suggestion_candidate(project_id)
        if candidate is None:
            return self._empty(project_id, project_title)

        entity = candidate.get("entity") or {}
        name = str(entity.get("name") or "").strip()
        relation_capabilities = set(candidate.get("relation_capabilities") or [])
        property_capabilities = set(candidate.get("property_capabilities") or [])
        suggestions = [
            QaSuggestion(
                id=f"relation:{capability}",
                question=template.format(name=name),
                kind="relation",
                capability=capability,
            )
            for capability, template in RELATION_QUESTIONS
            if capability in relation_capabilities
        ]
        suggestions.extend(
            QaSuggestion(
                id=f"attribute:{capability}",
                question=template.format(name=name),
                kind="attribute",
                capability=capability,
            )
            for capability, template in ATTRIBUTE_QUESTIONS
            if capability in property_capabilities
        )
        suggestions = suggestions[:6]
        if not name or not suggestions:
            return self._empty(project_id, project_title)
        return QaSuggestionsResponse(
            project_id=project_id,
            project_title=project_title,
            representative_entity=QaRepresentativeEntity.model_validate(entity),
            suggestions=suggestions,
        )

    @staticmethod
    def _empty(project_id: str, project_title: str) -> QaSuggestionsResponse:
        return QaSuggestionsResponse(
            project_id=project_id,
            project_title=project_title,
        )
