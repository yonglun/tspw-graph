from dataclasses import dataclass

from app.qa.intents import parse_local_intent


@dataclass(frozen=True)
class QueryTemplate:
    relation: str
    entity_role: str
    explanation: str
    cypher: str


RELATION_TEMPLATES = {
    "master": QueryTemplate(
        relation="MASTER_OF",
        entity_role="target",
        explanation="查找以该人物为弟子的师承事实。",
        cypher="MATCH (source:Entity {project_id: $project_id})<-[:SOURCE]-(fact:Fact {project_id: $project_id, type: 'MASTER_OF'})-[:TARGET]->(target:Entity {project_id: $project_id, id: $entity_id}) WHERE coalesce(fact.review_status, 'ACCEPTED') <> 'REJECTED' RETURN source, fact",
    ),
    "martial_art": QueryTemplate(
        relation="KNOWS",
        entity_role="source",
        explanation="查找该人物作为主体的武学掌握事实。",
        cypher="MATCH (source:Entity {project_id: $project_id, id: $entity_id})<-[:SOURCE]-(fact:Fact {project_id: $project_id, type: 'KNOWS'})-[:TARGET]->(target:Entity {project_id: $project_id}) WHERE coalesce(fact.review_status, 'ACCEPTED') <> 'REJECTED' RETURN target, fact",
    ),
    "organization": QueryTemplate(
        relation="MEMBER_OF",
        entity_role="source",
        explanation="查找该人物作为主体的组织隶属事实。",
        cypher="MATCH (source:Entity {project_id: $project_id, id: $entity_id})<-[:SOURCE]-(fact:Fact {project_id: $project_id, type: 'MEMBER_OF'})-[:TARGET]->(target:Entity {project_id: $project_id}) WHERE coalesce(fact.review_status, 'ACCEPTED') <> 'REJECTED' RETURN target, fact",
    ),
}


def classify(question: str) -> str | None:
    intent = parse_local_intent(question)
    if intent is None:
        return None
    return {
        "MASTER_OF": "master",
        "KNOWS": "martial_art",
        "MEMBER_OF": "organization",
    }.get(intent.relation or "", "introduction" if intent.intent == "INTRODUCTION" else None)


def subject_text(question: str) -> str:
    intent = parse_local_intent(question)
    if intent is not None:
        return intent.subject
    return question.strip().rstrip("？?")
