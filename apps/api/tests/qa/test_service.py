from typing import Any

from app.qa.service import QaService


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
                "rows": [{"id": "f1", "type": "MASTER_OF", "source_id": "yue", "target_id": "linghu", "evidence": EVIDENCE}],
            }
        if entity_id == "yue":
            return {"entity": {"id": "yue", "project_id": project_id, "type": "Person", "name": "嶽不群", "aliases": ["岳不群"], "description": "华山派掌门。"}, "rows": []}
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


def test_exact_subject_match_wins_when_search_returns_containing_entities() -> None:
    answer = QaService(AmbiguousSearchRepository()).ask("xiaoao", "令狐冲的师父是谁？")

    assert answer.answer == "令狐冲的师父是嶽不群。"
    assert answer.parameters["entity_id"] == "linghu"
    assert "$project_id" in answer.cypher_template


def test_no_result_does_not_invent() -> None:
    answer = QaService(FakeRepository()).ask("xiaoao", "令狐冲的生日是哪天？")

    assert answer.answer == "图谱中暂无足够事实"
    assert answer.evidence == []
