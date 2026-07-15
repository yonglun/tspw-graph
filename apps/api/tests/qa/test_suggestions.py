from app.qa.suggestions import QaSuggestionService


class Repository:
    def __init__(self, candidate):
        self.candidate = candidate
        self.calls = []

    def qa_suggestion_candidate(self, project_id: str):
        self.calls.append(project_id)
        return self.candidate


def test_builds_ordered_questions_from_supported_capabilities() -> None:
    repository = Repository(
        {
            "entity": {"id": "chen", "name": "陈家洛", "type": "Person"},
            "relation_capabilities": ["KNOWS", "MEMBER_OF", "MASTER_OF"],
            "property_capabilities": [
                "characteristic",
                "honorific",
                "identity",
                "gender",
            ],
        }
    )

    response = QaSuggestionService(repository).suggest("project-book", "书剑恩仇录")

    assert response.project_id == "project-book"
    assert response.project_title == "书剑恩仇录"
    assert response.representative_entity is not None
    assert response.representative_entity.name == "陈家洛"
    assert [item.capability for item in response.suggestions] == [
        "MASTER_OF",
        "MEMBER_OF",
        "KNOWS",
        "gender",
        "identity",
        "honorific",
    ]
    assert response.suggestions[0].question == "陈家洛的师父是谁？"
    assert len(response.suggestions) == 6
    assert repository.calls == ["project-book"]


def test_returns_empty_response_without_answerable_candidate() -> None:
    response = QaSuggestionService(Repository(None)).suggest("empty", "空项目")

    assert response.project_title == "空项目"
    assert response.representative_entity is None
    assert response.suggestions == []


def test_ignores_unknown_capabilities() -> None:
    response = QaSuggestionService(
        Repository(
            {
                "entity": {"id": "person", "name": "人物", "type": "Person"},
                "relation_capabilities": ["ALLY_OF"],
                "property_capabilities": ["birthday"],
            }
        )
    ).suggest("project", "小说")

    assert response.representative_entity is None
    assert response.suggestions == []
