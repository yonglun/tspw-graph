from typing import Any

from app.extraction.providers import ProviderError
from app.graph.models import EvidenceDetail
from app.ontology.catalog import CATALOG
from app.qa.intents import QaIntent, normalize_question, parse_local_intent
from app.qa.models import AskResponse, QaPathStep
from app.qa.templates import RELATION_TEMPLATES


NO_FACTS = "图谱中暂无足够事实"


class QaService:
    def __init__(self, repository: Any, intent_provider: Any | None = None) -> None:
        self.repository = repository
        self.intent_provider = intent_provider

    def ask(self, project_id: str, question: str) -> AskResponse:
        intent = parse_local_intent(question)
        if intent is None and self.intent_provider is not None:
            try:
                intent = self.intent_provider.parse(question, CATALOG)
            except ProviderError:
                return self._empty(project_id)
        if intent is None:
            return self._empty(project_id)

        if intent.intent == "UNSUPPORTED":
            return self._empty(project_id)
        if intent.subject and intent.subject not in normalize_question(question):
            return self._empty(project_id)

        subject = intent.subject
        matches = self.repository.search(project_id, subject, [], 5)
        entity = self._resolve_subject(matches, subject)
        if entity is None:
            return self._empty(project_id)

        if intent.intent == "INTRODUCTION":
            description = entity.get("description", "").strip()
            if not description:
                return self._empty(project_id)
            return AskResponse(
                answer=f"{entity['name']}：{description}",
                query_explanation="按规范名或别名定位人物实体并读取简介。",
                cypher_template="MATCH (entity:Entity {project_id: $project_id, id: $entity_id}) RETURN entity",
                parameters={"project_id": project_id, "entity_id": entity["id"]},
            )

        detail = self.repository.entity_detail(project_id, entity["id"])
        if detail is None:
            return self._empty(project_id)
        if intent.intent == "ATTRIBUTE":
            return self._attribute_answer(entity, detail, intent)

        template_key = next(
            (key for key, item in RELATION_TEMPLATES.items() if item.relation == intent.relation),
            None,
        )
        if template_key is None:
            return self._empty(project_id)
        template = RELATION_TEMPLATES[template_key]
        related_matches: dict[str, dict[str, Any]] = {}
        for row in detail["rows"]:
            if row.get("review_status") == "REJECTED":
                continue
            if row.get("type") != template.relation:
                continue
            if template.entity_role == "source" and row.get("source_id") != entity["id"]:
                continue
            if template.entity_role == "target" and row.get("target_id") != entity["id"]:
                continue
            related_id = (
                row["source_id"]
                if template.entity_role == "target"
                else row["target_id"]
            )
            related_entity = row.get(
                "source" if template.entity_role == "target" else "target"
            )
            if not related_entity or not related_entity.get("name"):
                related = self.repository.entity_detail(project_id, related_id)
                if related is None:
                    continue
                related_entity = related["entity"]
            match = related_matches.setdefault(
                related_id,
                {"entity": related_entity, "evidence": []},
            )
            evidence = row.get("evidence")
            if evidence and evidence.get("id"):
                match["evidence"].append(EvidenceDetail.model_validate(evidence))
        if not related_matches:
            return self._empty(project_id)

        matches = list(related_matches.values())
        related_names = [match["entity"]["name"] for match in matches]
        path = [
            QaPathStep(
                source_name=(
                    match["entity"]["name"]
                    if template.entity_role == "target"
                    else entity["name"]
                ),
                relation=template.relation,
                target_name=(
                    entity["name"]
                    if template.entity_role == "target"
                    else match["entity"]["name"]
                ),
            )
            for match in matches
        ]
        evidence = list(
            {
                item.id: item
                for match in matches
                for item in match["evidence"]
            }.values()
        )
        return AskResponse(
            answer=self._answer_many(template_key, entity["name"], related_names),
            path=path,
            query_explanation=template.explanation,
            cypher_template=template.cypher,
            parameters={"project_id": project_id, "entity_id": entity["id"]},
            evidence=evidence,
        )

    def _attribute_answer(
        self,
        entity: dict[str, Any],
        detail: dict[str, Any],
        intent: QaIntent,
    ) -> AskResponse:
        attributes = [
            row
            for row in detail.get("attributes", [])
            if row.get("property_id") == intent.property
        ]
        evidence: list[EvidenceDetail] = []
        values: list[str] = []
        for attribute in attributes:
            attribute_evidence = [
                EvidenceDetail.model_validate(item)
                for item in attribute.get("evidence", [])
                if item.get("id")
            ]
            if not attribute_evidence:
                continue
            values.append(str(attribute.get("value", "")))
            evidence.extend(attribute_evidence)
        if not values:
            return self._empty(entity.get("project_id", ""))

        label = next(
            (
                definition_property.label
                for definition in CATALOG.entity_types
                for definition_property in definition.effective_property_definitions
                if definition_property.id == intent.property
            ),
            intent.property or "属性",
        )
        unique_values = list(dict.fromkeys(value for value in values if value))
        if not unique_values:
            return self._empty(entity.get("project_id", ""))
        return AskResponse(
            answer=f"{entity['name']}的{label}是{'、'.join(unique_values)}。",
            query_explanation="按实体属性断言读取，并要求至少一条原文证据。",
            cypher_template="MATCH (entity:Entity {project_id: $project_id, id: $entity_id})-[:HAS_ATTRIBUTE]->(attribute:AttributeAssertion) RETURN attribute",
            parameters={
                "project_id": entity.get("project_id", ""),
                "entity_id": entity["id"],
                "property_id": intent.property or "",
            },
            evidence=list({item.id: item for item in evidence}.values()),
        )

    def _answer(self, intent: str, entity_name: str, related_name: str) -> str:
        if intent == "master":
            return f"{entity_name}的师父是{related_name}。"
        if intent == "martial_art":
            return f"{entity_name}掌握{related_name}。"
        return f"{entity_name}隶属于{related_name}。"

    def _answer_many(self, intent: str, entity_name: str, related_names: list[str]) -> str:
        names = "、".join(dict.fromkeys(related_names))
        if intent == "master":
            return f"{entity_name}的师父是{names}。"
        if intent == "martial_art":
            return f"{entity_name}掌握{names}。"
        return f"{entity_name}隶属于{names}。"

    def _resolve_subject(
        self, matches: list[dict[str, Any]], subject: str
    ) -> dict[str, Any] | None:
        exact_name = [item for item in matches if item.get("name") == subject]
        if len(exact_name) == 1:
            return exact_name[0]

        exact_alias = [
            item
            for item in matches
            if subject
            in {
                alias
                for alias in item.get("aliases", [])
                if isinstance(alias, str)
            }
        ]
        if len(exact_alias) == 1:
            return exact_alias[0]

        if len(matches) == 1:
            return matches[0]
        return None

    def _empty(self, project_id: str) -> AskResponse:
        return AskResponse(
            answer=NO_FACTS,
            query_explanation="问题不属于受控模板，或图谱没有可验证事实。",
            cypher_template="",
            parameters={"project_id": project_id},
        )
