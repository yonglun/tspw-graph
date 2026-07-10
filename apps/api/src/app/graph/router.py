from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from neo4j.exceptions import Neo4jError, ServiceUnavailable

from app.graph.models import EntityDetail, EntitySummary, Neighborhood, TimelineEvent
from app.graph.repository import Neo4jGraphRepository
from app.graph.service import EntityNotFoundError, GraphService

router = APIRouter(tags=["graph"])


def get_repository(request: Request) -> Neo4jGraphRepository:
    return Neo4jGraphRepository(request.app.state.neo4j_driver)


Repository = Annotated[Neo4jGraphRepository, Depends(get_repository)]


def execute(call):
    try:
        return call()
    except EntityNotFoundError as error:
        raise HTTPException(
            status_code=404,
            detail={"code": "ENTITY_NOT_FOUND", "entity_id": str(error)},
        ) from error
    except (ServiceUnavailable, Neo4jError) as error:
        raise HTTPException(
            status_code=503, detail={"code": "GRAPH_UNAVAILABLE"}
        ) from error


@router.get("/api/graph/search", response_model=list[EntitySummary])
def search(
    repository: Repository,
    project_id: str,
    query: str = Query(min_length=1, max_length=100),
    types: list[str] = Query(default=[]),
    limit: int = Query(default=20, ge=1, le=50),
) -> list[EntitySummary]:
    return execute(lambda: GraphService(repository).search(project_id, query, types, limit))


@router.get("/api/graph/neighborhood", response_model=Neighborhood)
def neighborhood(
    repository: Repository,
    project_id: str,
    entity_id: str,
    depth: int = Query(default=1, ge=1, le=2),
    limit: int = Query(default=50, ge=1, le=100),
    from_chapter: int | None = Query(default=None, ge=1),
    to_chapter: int | None = Query(default=None, ge=1),
) -> Neighborhood:
    return execute(
        lambda: GraphService(repository).neighborhood(
            project_id, entity_id, depth, limit, from_chapter, to_chapter
        )
    )


@router.get("/api/graph/path", response_model=Neighborhood)
def path(
    repository: Repository,
    project_id: str,
    source_id: str,
    target_id: str,
    max_depth: int = Query(default=4, ge=1, le=6),
) -> Neighborhood:
    return execute(
        lambda: GraphService(repository).shortest_path(
            project_id, source_id, target_id, max_depth
        )
    )


@router.get("/api/graph/timeline", response_model=list[TimelineEvent])
def timeline(
    repository: Repository,
    project_id: str,
    person_id: str | None = None,
    from_chapter: int | None = Query(default=None, ge=1),
    to_chapter: int | None = Query(default=None, ge=1),
    limit: int = Query(default=50, ge=1, le=100),
) -> list[TimelineEvent]:
    return execute(
        lambda: GraphService(repository).timeline(
            project_id, person_id, from_chapter, to_chapter, limit
        )
    )


@router.get("/api/entities/{entity_id}", response_model=EntityDetail)
def entity_detail(
    repository: Repository, entity_id: str, project_id: str
) -> EntityDetail:
    return execute(lambda: GraphService(repository).entity_detail(project_id, entity_id))
