from __future__ import annotations

import json
import logging
from typing import Any

import httpx
from pydantic import ValidationError

from app.extraction.providers import ProviderError, ProviderErrorKind, parse_retry_after_seconds
from app.ontology.models import OntologyCatalog
from app.qa.intents import QaIntent


logger = logging.getLogger(__name__)
MIN_CONFIDENCE = 0.70


class QaIntentProvider:
    def __init__(
        self,
        *,
        base_url: str,
        deployment: str,
        api_version: str,
        api_key: str,
        timeout_seconds: float = 30,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.deployment = deployment
        self.api_version = api_version
        self.api_key = api_key
        self.client = client or httpx.Client(timeout=timeout_seconds)

    def parse(self, question: str, catalog: OntologyCatalog) -> QaIntent:
        relation_ids = [item.id.value for item in catalog.relation_types]
        property_ids = sorted(
            {
                prop.id
                for entity in catalog.entity_types
                for prop in entity.effective_property_definitions
            }
        )
        try:
            response = self.client.post(
                f"{self.base_url}/openai/deployments/{self.deployment}/chat/completions",
                params={"api-version": self.api_version},
                headers={"api-key": self.api_key},
                json={
                    "messages": [
                        {
                            "role": "system",
                            "content": self._system_prompt(relation_ids, property_ids),
                        },
                        {"role": "user", "content": question},
                    ],
                    "response_format": {
                        "type": "json_schema",
                        "json_schema": {
                            "name": "qa_intent",
                            "strict": True,
                            "schema": self._schema(relation_ids, property_ids),
                        },
                    },
                },
            )
        except httpx.HTTPError as error:
            raise ProviderError(
                ProviderErrorKind.RETRYABLE, "QA_MODEL_NETWORK_ERROR"
            ) from error
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as error:
            status = error.response.status_code
            kind = ProviderErrorKind.RETRYABLE if status == 429 or status >= 500 else ProviderErrorKind.INVALID_RESPONSE
            logger.warning("QA intent model HTTP error status=%s deployment=%s", status, self.deployment)
            raise ProviderError(
                kind,
                f"QA_MODEL_HTTP_{status}",
                retry_after_seconds=parse_retry_after_seconds(error.response.headers),
            ) from error
        try:
            content = response.json()["choices"][0]["message"]["content"]
            intent = QaIntent.model_validate_json(content)
        except (KeyError, TypeError, ValueError, ValidationError) as error:
            raise ProviderError(ProviderErrorKind.INVALID_RESPONSE, "MODEL_RESPONSE_INVALID") from error
        if intent.confidence < MIN_CONFIDENCE:
            raise ProviderError(ProviderErrorKind.INVALID_RESPONSE, "QA_INTENT_LOW_CONFIDENCE")
        if intent.relation is not None and intent.relation not in relation_ids:
            raise ProviderError(ProviderErrorKind.INVALID_RESPONSE, "QA_INTENT_INVALID")
        if intent.property is not None and intent.property not in property_ids:
            raise ProviderError(ProviderErrorKind.INVALID_RESPONSE, "QA_INTENT_INVALID")
        return intent

    @staticmethod
    def _system_prompt(relation_ids: list[str], property_ids: list[str]) -> str:
        return (
            "将用户问题解析为知识图谱查询意图。只输出 JSON，不回答事实，不生成 Cypher。"
            f"允许的关系 ID：{json.dumps(relation_ids, ensure_ascii=False)}。"
            f"允许的属性 ID：{json.dumps(property_ids, ensure_ascii=False)}。"
            "intent 只能是 RELATION、ATTRIBUTE、INTRODUCTION 或 UNSUPPORTED。"
        )

    @staticmethod
    def _schema(relation_ids: list[str], property_ids: list[str]) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "intent": {
                    "type": "string",
                    "enum": ["RELATION", "ATTRIBUTE", "INTRODUCTION", "UNSUPPORTED"],
                },
                "subject": {"type": "string"},
                "relation": {"type": ["string", "null"], "enum": relation_ids + [None]},
                "property": {"type": ["string", "null"], "enum": property_ids + [None]},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            },
            "required": ["intent", "subject", "relation", "property", "confidence"],
            "additionalProperties": False,
        }
