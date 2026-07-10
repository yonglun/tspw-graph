from app.extraction.models import (
    CandidateAttribute,
    CandidateEntity,
    CandidateEvidence,
    CandidateFact,
    ExtractionRequest,
    ExtractionResult,
)


class FixedProvider:
    def __init__(self, result: ExtractionResult | None = None) -> None:
        self.result = result

    def extract(self, request: ExtractionRequest) -> ExtractionResult:
        result = self.result or self._fixture_result(request.text)
        return result.model_copy(deep=True)

    @staticmethod
    def _fixture_result(text: str) -> ExtractionResult:
        relation_quote = "测试人物甲认识测试人物乙"
        relation_start = text.find(relation_quote)
        identity_value = "华山派大弟子"
        identity_start = text.find(identity_value)
        has_person_a = relation_start >= 0 or (
            identity_start >= 0 and "测试人物甲" in text
        )

        entities = []
        if has_person_a:
            entities.append(
                CandidateEntity(local_id="person-a", name="测试人物甲", type="Person")
            )
        if relation_start >= 0:
            entities.append(
                CandidateEntity(local_id="person-b", name="测试人物乙", type="Person")
            )

        facts = []
        if relation_start >= 0:
            facts.append(
                CandidateFact(
                    relation="KNOWS",
                    source_local_id="person-a",
                    target_local_id="person-b",
                    evidence=CandidateEvidence(
                        start=relation_start,
                        end=relation_start + len(relation_quote),
                        quote=relation_quote,
                    ),
                )
            )

        attributes = []
        if has_person_a and identity_start >= 0:
            attributes.append(
                CandidateAttribute(
                    entity_local_id="person-a",
                    property_id="identity",
                    value=identity_value,
                    evidence=CandidateEvidence(
                        start=identity_start,
                        end=identity_start + len(identity_value),
                        quote=identity_value,
                    ),
                )
            )

        return ExtractionResult(
            entities=entities,
            facts=facts,
            attributes=attributes,
        )
