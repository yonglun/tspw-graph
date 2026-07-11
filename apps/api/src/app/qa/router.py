from fastapi import APIRouter, Depends, Request

from app.graph.repository import Neo4jGraphRepository
from app.graph.router import execute, get_repository
from app.qa.models import AskRequest, AskResponse
from app.qa.service import QaService

router = APIRouter(prefix="/api/ask", tags=["qa"])


def get_intent_provider(request: Request):
    return getattr(request.app.state, "qa_intent_provider", None)


@router.post("", response_model=AskResponse)
def ask(
    request: AskRequest,
    repository: Neo4jGraphRepository = Depends(get_repository),
    intent_provider=Depends(get_intent_provider),
) -> AskResponse:
    return execute(
        lambda: QaService(repository, intent_provider).ask(
            request.project_id, request.question
        )
    )
