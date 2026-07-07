from app.ontology.models import (
    EntityType as E,
    EntityTypeDefinition as Entity,
    OntologyCatalog,
    RelationType as R,
    RelationTypeDefinition as Relation,
    TripleExample,
)


def entity(
    id: E, label: str, description: str, color: str, parent: E | None = None
) -> Entity:
    return Entity(
        id=id, label=label, description=description, color=color, parent=parent
    )


def relation(
    id: R,
    label: str,
    description: str,
    source: tuple[E, ...],
    target: tuple[E, ...],
    *,
    symmetric: bool = False,
    temporal: bool = False,
) -> Relation:
    return Relation(
        id=id,
        label=label,
        description=description,
        source_types=source,
        target_types=target,
        symmetric=symmetric,
        temporal=temporal,
    )


CATALOG = OntologyCatalog(
    entity_types=(
        entity(E.PERSON, "人物", "小说中的人物角色", "#4f46e5"),
        entity(E.ORGANIZATION, "组织", "由人物组成的社会组织", "#059669"),
        entity(E.SECT, "门派", "武林门派", "#10b981", E.ORGANIZATION),
        entity(E.CLAN, "家族", "以亲缘关系形成的组织", "#34d399", E.ORGANIZATION),
        entity(E.ESCORT_AGENCY, "镖局", "从事护送业务的组织", "#6ee7b7", E.ORGANIZATION),
        entity(E.POLITICAL_FORCE, "政治势力", "朝廷或政治组织", "#047857", E.ORGANIZATION),
        entity(E.MARTIAL_ART, "武学", "武功、内功与技法", "#d97706"),
        entity(E.SWORDPLAY, "剑法", "以剑为主要载体的武学", "#f59e0b", E.MARTIAL_ART),
        entity(E.INTERNAL_SKILL, "内功", "修炼内力的武学", "#fbbf24", E.MARTIAL_ART),
        entity(E.PALM_TECHNIQUE, "掌法", "拳掌类武学", "#fcd34d", E.MARTIAL_ART),
        entity(E.QINGGONG, "轻功", "身法与移动类武学", "#fde68a", E.MARTIAL_ART),
        entity(E.MUSIC_SCORE, "曲谱", "以音乐为载体的武学或谱曲", "#fef3c7", E.MARTIAL_ART),
        entity(E.EVENT, "事件", "剧情中发生的事件", "#dc2626"),
        entity(E.TEACHING_EVENT, "传授事件", "人物传授武学的三元事件", "#ef4444", E.EVENT),
        entity(E.PLACE, "地点", "事件发生或人物活动的地点", "#0891b2"),
        entity(E.ARTIFACT, "物品", "兵器、秘籍与信物", "#7c3aed"),
    ),
    relation_types=(
        relation(R.MEMBER_OF, "隶属", "人物隶属于组织", (E.PERSON,), (E.ORGANIZATION,), temporal=True),
        relation(R.MASTER_OF, "师父", "人物是另一人物的师父", (E.PERSON,), (E.PERSON,)),
        relation(R.KIN_OF, "亲属", "人物之间的亲属关系", (E.PERSON,), (E.PERSON,), symmetric=True),
        relation(R.ALLY_OF, "盟友", "人物或组织之间的盟友关系", (E.PERSON, E.ORGANIZATION), (E.PERSON, E.ORGANIZATION), symmetric=True, temporal=True),
        relation(R.ENEMY_OF, "敌对", "人物或组织之间的敌对关系", (E.PERSON, E.ORGANIZATION), (E.PERSON, E.ORGANIZATION), symmetric=True, temporal=True),
        relation(R.KNOWS, "掌握", "人物掌握一项武学", (E.PERSON,), (E.MARTIAL_ART,)),
        relation(R.TEACHER, "传授者", "传授事件的传授者", (E.TEACHING_EVENT,), (E.PERSON,)),
        relation(R.STUDENT, "学习者", "传授事件的学习者", (E.TEACHING_EVENT,), (E.PERSON,)),
        relation(R.SUBJECT, "传授内容", "传授事件涉及的武学", (E.TEACHING_EVENT,), (E.MARTIAL_ART,)),
        relation(R.HOLDS, "持有", "人物持有物品", (E.PERSON,), (E.ARTIFACT,), temporal=True),
        relation(R.PARTICIPATES_IN, "参与", "人物或组织参与事件", (E.PERSON, E.ORGANIZATION), (E.EVENT,)),
        relation(R.OCCURS_AT, "发生于", "事件发生于地点", (E.EVENT,), (E.PLACE,)),
    ),
    example=TripleExample(subject="令狐冲", predicate=R.KNOWS, object="独孤九剑"),
)


def relation_by_id(relation_id: str) -> Relation | None:
    return next((item for item in CATALOG.relation_types if item.id == relation_id), None)
