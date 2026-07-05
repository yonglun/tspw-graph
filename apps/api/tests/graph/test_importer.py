from collections import defaultdict
from typing import Any

from app.graph.importer import GraphImporter
from app.graph.models import GraphDocument


class FakeGraph:
    def __init__(self) -> None:
        self.records: dict[str, set[str]] = defaultdict(set)

    def ensure_constraints(self) -> None:
        return None

    def upsert_batch(self, label: str, rows: list[dict[str, Any]]) -> int:
        created = 0
        for row in rows:
            key = str(row["id"])
            if key not in self.records[label]:
                self.records[label].add(key)
                created += 1
        return created

    def count(self, label: str) -> int:
        return len(self.records[label])


def sample_document() -> GraphDocument:
    return GraphDocument.model_validate(
        {
            "project": {"id": "xiaoao", "title": "笑傲江湖"},
            "chapters": [{"id": "xiaoao:chapter:1", "number": 1, "title": "灭门"}],
            "entities": [
                {"id": "xiaoao:person:linghuchong", "type": "Person", "name": "令狐冲", "aliases": []},
                {"id": "xiaoao:person:yuebuqun", "type": "Person", "name": "岳不群", "aliases": []},
                {"id": "xiaoao:sect:huashan", "type": "Sect", "name": "华山派", "aliases": []},
            ],
            "facts": [
                {"id": "xiaoao:fact:master", "type": "MASTER_OF", "source_id": "xiaoao:person:yuebuqun", "target_id": "xiaoao:person:linghuchong", "evidence_ids": ["xiaoao:evidence:1"]},
                {"id": "xiaoao:fact:member", "type": "MEMBER_OF", "source_id": "xiaoao:person:linghuchong", "target_id": "xiaoao:sect:huashan", "evidence_ids": ["xiaoao:evidence:2"]},
            ],
            "evidence": [
                {"id": "xiaoao:evidence:1", "chapter_id": "xiaoao:chapter:1", "start_offset": 0, "end_offset": 3, "quote": "令狐冲", "text_hash": "hash-1"},
                {"id": "xiaoao:evidence:2", "chapter_id": "xiaoao:chapter:1", "start_offset": 4, "end_offset": 7, "quote": "华山派", "text_hash": "hash-2"},
            ],
        }
    )


def test_importing_same_document_twice_is_idempotent() -> None:
    fake_graph = FakeGraph()
    importer = GraphImporter(fake_graph)

    first = importer.import_document(sample_document())
    second = importer.import_document(sample_document())

    assert first.created_entities == 3
    assert first.created_facts == 2
    assert first.created_evidence == 2
    assert second.created_entities == 0
    assert second.created_facts == 0
    assert second.created_evidence == 0
    assert fake_graph.count("Entity") == 3
    assert fake_graph.count("Fact") == 2
    assert fake_graph.count("Evidence") == 2
