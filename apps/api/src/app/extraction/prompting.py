from app.extraction.models import ExtractionRequest
from app.ontology.catalog import CATALOG, relation_by_id


RELATION_HINTS = {
    "MASTER_OF": (
        "方向固定为 师父 -> 徒弟。触发词包括：师父、师傅、师尊、弟子、徒弟、大弟子、二师弟。"
    ),
    "SPOUSE_OF": (
        "对称关系，表示夫妻、丈夫、妻子、夫人。触发词包括：妻子、丈夫、夫人、夫妇、成婚。"
    ),
    "KIN_OF": "亲属关系，不要把明确夫妻关系放入 KIN_OF，夫妻优先使用 SPOUSE_OF。",
    "MEMBER_OF": "方向固定为 人物 -> 组织/门派。",
    "KNOWS": "方向固定为 人物 -> 武学。",
    "TEACHER": "方向固定为 传授事件 -> 传授者。",
    "STUDENT": "方向固定为 传授事件 -> 学习者。",
    "SUBJECT": "方向固定为 传授事件 -> 传授内容。",
}


def extraction_system_prompt(request: ExtractionRequest) -> str:
    relation_ids = set(request.ontology.get("relation_types", []))
    entity_ids = set(request.ontology.get("entity_types", []))
    entities = [
        f"- {item.id.value}: {item.label}。{item.description}"
        for item in CATALOG.entity_types
        if not entity_ids or item.id.value in entity_ids
    ]
    relations = []
    for relation_id in sorted(relation_ids):
        relation = relation_by_id(relation_id)
        if relation is None:
            continue
        source_types = ", ".join(item.value for item in relation.source_types)
        target_types = ", ".join(item.value for item in relation.target_types)
        hint = RELATION_HINTS.get(relation.id.value, "")
        relations.append(
            f"- {relation.id.value}: {relation.label}。{relation.description} "
            f"({source_types} -> {target_types})。{hint}"
        )

    return "\n".join(
        [
            "你是小说知识图谱抽取器。只抽取文本中有原文证据支持的实体和事实，不要补常识，不要改写原文。",
            "输出必须符合 JSON schema。",
            "证据要求：每个 fact 的 evidence.start/end 必须精确定位 quote；"
            "quote 必须逐字等于 text[start:end]，不能省略、繁简转换或改写。",
            "实体类型：",
            *entities,
            "关系类型和方向规则：",
            *relations,
            "抽取要求：",
            "- 如果文本说“X的师父是Y”，输出 MASTER_OF: Y -> X。",
            "- 如果文本说“Y是X的师父”，输出 MASTER_OF: Y -> X。",
            "- 如果文本说“X是Y的妻子/夫人”或“Y的妻子是X”，输出 SPOUSE_OF: X -> Y。",
            "- 如果关系类型不在允许列表中，不要输出该 fact。",
        ]
    )
