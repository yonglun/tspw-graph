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
