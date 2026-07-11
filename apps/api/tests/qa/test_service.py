from typing import Any

from app.qa.service import QaService
from app.qa.intents import QaIntent


EVIDENCE = {
    "id": "e1",
    "chapter_id": "c5",
    "chapter_number": 5,
    "chapter_title": "治傷",
    "start_offset": 10,
    "end_offset": 20,
    "quote": "君子劍嶽先生的嫡派傳人",
}


class FakeRepository:
    def search(self, project_id: str, query: str, types: list[str], limit: int):
        if "生日" in query:
            return []
        return [{"id": "linghu", "project_id": project_id, "type": "Person", "name": "令狐沖", "aliases": ["令狐冲"], "description": "华山派大弟子。"}]

    def entity_detail(self, project_id: str, entity_id: str) -> dict[str, Any] | None:
        if entity_id == "linghu":
            return {
                "entity": {"id": "linghu", "project_id": project_id, "type": "Person", "name": "令狐沖", "aliases": [], "description": "华山派大弟子。"},
                "attributes": [
                    {
                        "id": "a-gender",
                        "property_id": "gender",
                        "label": "性别",
                        "value_type": "ENUM",
                        "value": "男",
                        "confidence": 1.0,
                        "evidence": [EVIDENCE],
                    },
                    {
                        "id": "a-honorific",
                        "property_id": "honorific",
                        "label": "称号",
                        "value_type": "TEXT",
                        "value": "令狐少侠",
                        "confidence": 1.0,
                        "evidence": [EVIDENCE],
                    },
                ],
                "rows": [
                    {"id": "f1", "type": "MASTER_OF", "source_id": "yue", "target_id": "linghu", "evidence": EVIDENCE},
                    {"id": "f2", "type": "MEMBER_OF", "source_id": "linghu", "target_id": "huashan", "evidence": EVIDENCE},
                ],
            }
        if entity_id == "yue":
            return {"entity": {"id": "yue", "project_id": project_id, "type": "Person", "name": "嶽不群", "aliases": ["岳不群"], "description": "华山派掌门。"}, "rows": []}
        if entity_id == "huashan":
            return {"entity": {"id": "huashan", "project_id": project_id, "type": "Sect", "name": "华山派", "aliases": [], "description": ""}, "rows": []}
        return None


class AmbiguousSearchRepository(FakeRepository):
    def search(self, project_id: str, query: str, types: list[str], limit: int):
        return [
            {
                "id": "linghu-chong-en",
                "project_id": project_id,
                "type": "Person",
                "name": "Linghu Chong",
                "aliases": ["令狐冲"],
                "description": "",
            },
            {
                "id": "linghu-father",
                "project_id": project_id,
                "type": "Person",
                "name": "令狐冲的父親",
                "aliases": [],
                "description": "",
            },
            {
                "id": "linghu",
                "project_id": project_id,
                "type": "Person",
                "name": "令狐冲",
                "aliases": ["令狐沖"],
                "description": "华山派大弟子。",
            },
        ]

    def entity_detail(self, project_id: str, entity_id: str) -> dict[str, Any] | None:
        if entity_id == "linghu":
            return {
                "entity": {
                    "id": "linghu",
                    "project_id": project_id,
                    "type": "Person",
                    "name": "令狐冲",
                    "aliases": ["令狐沖"],
                    "description": "华山派大弟子。",
                },
                "rows": [
                    {
                        "id": "f1",
                        "type": "MASTER_OF",
                        "source_id": "yue",
                        "target_id": "linghu",
                        "evidence": EVIDENCE,
                    }
                ],
            }
        if entity_id == "yue":
            return {
                "entity": {
                    "id": "yue",
                    "project_id": project_id,
                    "type": "Person",
                    "name": "嶽不群",
                    "aliases": ["岳不群"],
                    "description": "华山派掌门。",
                },
                "rows": [],
            }
        return None


def test_answer_includes_path_and_evidence() -> None:
    answer = QaService(FakeRepository()).ask("xiaoao", "令狐冲的师父是谁？")

    assert "嶽不群" in answer.answer
    assert answer.path
    assert answer.evidence[0].chapter_id == "c5"
    assert "$project_id" in answer.cypher_template


def test_relation_answer_includes_all_matching_targets_and_evidence() -> None:
    class MultiFactRepository(FakeRepository):
        def entity_detail(self, project_id: str, entity_id: str) -> dict[str, Any] | None:
            detail = super().entity_detail(project_id, entity_id)
            if entity_id == "linghu":
                assert detail is not None
                detail["rows"] = [
                    {"id": "f-sword", "type": "KNOWS", "source_id": "linghu", "target_id": "sword-1", "target": {"id": "sword-1", "name": "独孤九剑"}, "evidence": EVIDENCE},
                    {"id": "f-sword-2", "type": "KNOWS", "source_id": "linghu", "target_id": "sword-2", "target": {"id": "sword-2", "name": "吸星大法"}, "evidence": {**EVIDENCE, "id": "e2", "quote": "吸星大法"}},
                ]
            if entity_id in {"sword-1", "sword-2"}:
                return {"entity": {"id": entity_id, "project_id": project_id, "type": "Swordplay", "name": "独孤九剑" if entity_id == "sword-1" else "吸星大法", "aliases": [], "description": ""}, "rows": []}
            return detail

    answer = QaService(MultiFactRepository()).ask("xiaoao", "令狐冲掌握什么武功？")

    assert answer.answer == "令狐沖掌握独孤九剑、吸星大法。"
    assert [step.target_name for step in answer.path] == ["独孤九剑", "吸星大法"]
    assert {item.id for item in answer.evidence} == {"e1", "e2"}


def test_exact_subject_match_wins_when_search_returns_containing_entities() -> None:
    answer = QaService(AmbiguousSearchRepository()).ask("xiaoao", "令狐冲的师父是谁？")

    assert answer.answer == "令狐冲的师父是嶽不群。"
    assert answer.parameters["entity_id"] == "linghu"
    assert "$project_id" in answer.cypher_template


def test_no_result_does_not_invent() -> None:
    answer = QaService(FakeRepository()).ask("xiaoao", "令狐冲的生日是哪天？")

    assert answer.answer == "图谱中暂无足够事实"
    assert answer.evidence == []


def test_attribute_answer_includes_value_and_evidence() -> None:
    answer = QaService(FakeRepository()).ask("xiaoao", "令狐冲的性别是什么？")

    assert answer.answer == "令狐沖的性别是男。"
    assert answer.path == []
    assert answer.evidence[0].id == "e1"


def test_relation_synonyms_resolve_the_subject() -> None:
    repository = FakeRepository()

    for question in ("令狐冲隶属于什么门派？", "令狐冲属于哪个门派？"):
        answer = QaService(repository).ask("xiaoao", question)
        assert answer.answer == "令狐沖隶属于华山派。"
        assert answer.path[0].relation == "MEMBER_OF"


def test_llm_provider_is_only_used_for_unrecognized_questions() -> None:
    class Provider:
        def __init__(self):
            self.calls = 0

        def parse(self, question, catalog):
            self.calls += 1
            return QaIntent(
                intent="ATTRIBUTE",
                subject="令狐冲",
                property="gender",
            )

    provider = Provider()
    repository = FakeRepository()
    local = QaService(repository, provider).ask("xiaoao", "令狐冲的性别是什么？")
    fallback = QaService(repository, provider).ask("xiaoao", "请告诉我令狐冲是男的吗？")

    assert provider.calls == 1
    assert local.answer == "令狐沖的性别是男。"
    assert fallback.answer == "令狐沖的性别是男。"
