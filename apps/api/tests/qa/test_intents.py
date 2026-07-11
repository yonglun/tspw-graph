from app.qa.intents import parse_local_intent


def test_parses_membership_question_without_de() -> None:
    intent = parse_local_intent("令狐冲隶属于什么门派？")

    assert intent is not None
    assert intent.intent == "RELATION"
    assert intent.subject == "令狐冲"
    assert intent.relation == "MEMBER_OF"
    assert intent.property is None


def test_parses_membership_synonym() -> None:
    intent = parse_local_intent("令狐冲属于哪个门派？")

    assert intent is not None
    assert intent.subject == "令狐冲"
    assert intent.relation == "MEMBER_OF"


def test_parses_attribute_questions() -> None:
    gender = parse_local_intent("请问令狐冲的性别是什么？")
    honorific = parse_local_intent("令狐冲有哪些称号？")

    assert gender is not None
    assert gender.intent == "ATTRIBUTE"
    assert gender.subject == "令狐冲"
    assert gender.property == "gender"
    assert honorific is not None
    assert honorific.property == "honorific"


def test_existing_master_question_is_preserved() -> None:
    intent = parse_local_intent("令狐冲的师父是谁？")

    assert intent is not None
    assert intent.relation == "MASTER_OF"
    assert intent.subject == "令狐冲"


def test_unsupported_question_returns_none() -> None:
    assert parse_local_intent("令狐冲的生日是哪天？") is None
