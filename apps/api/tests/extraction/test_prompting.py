from app.extraction.models import ExtractionRequest
from app.extraction.prompting import extraction_system_prompt


def test_extraction_prompt_includes_relation_labels_and_direction_rules():
    prompt = extraction_system_prompt(
        ExtractionRequest(
            project_id="p-1",
            chunk_id="c-1",
            text="令狐冲的师父是岳不群。岳夫人是岳不群的妻子。",
            ontology={
                "entity_types": ["Person"],
                "relation_types": ["MASTER_OF", "SPOUSE_OF"],
            },
        )
    )

    assert "MASTER_OF" in prompt
    assert "师父 -> 徒弟" in prompt
    assert "SPOUSE_OF" in prompt
    assert "妻子" in prompt
    assert "start/end 必须精确定位 quote" in prompt
    assert "quote 必须少于 500 字" in prompt


def test_extraction_prompt_includes_effective_property_contract_and_rules():
    prompt = extraction_system_prompt(
        ExtractionRequest(
            project_id="p-1",
            chunk_id="c-1",
            text="令狐冲是华山派大弟子。",
            ontology={"entity_types": ["Person"], "relation_types": []},
        )
    )

    assert "- Person.identity（身份，TEXT，可多值）：人物的身份或社会角色" in prompt
    assert "只允许使用上述属性 ID" in prompt
    assert "存在关系类型时，不要把另一个实体作为属性值" in prompt
    assert (
        "师父/徒弟、丈夫/妻子/配偶、成员/所属、掌握武学、参与事件、持有物品"
        "都必须建模为关系，不能作为 identity、honorific 或其他属性值"
    ) in prompt
    assert "不确定的属性值不要输出" in prompt
    assert "能证明属性值的最短原文片段" in prompt
