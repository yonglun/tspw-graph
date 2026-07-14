from contextlib import asynccontextmanager

from fastapi import FastAPI
from neo4j import GraphDatabase

from app.auth.dependencies import build_auth_service
from app.auth.router import router as auth_router

from app.graph.router import router as graph_router
from app.extraction.router import router as extraction_router
from app.extraction.providers import ProviderError, ProviderRegistry
from app.jobs.router import router as jobs_router
from app.ontology.router import router as ontology_router
from app.projects.router import router as projects_router
from app.qa.router import router as qa_router
from app.review.router import router as review_router
from app.settings import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    app.state.auth_service = build_auth_service(settings)
    app.state.auth_service.bootstrap_default_admin()
    driver = GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
    )
    app.state.neo4j_driver = driver
    try:
        app.state.qa_intent_provider = ProviderRegistry(settings).create_qa_intent(
            settings.qa_model_profile_id
        )
    except ProviderError:
        app.state.qa_intent_provider = None
    try:
        yield
    finally:
        driver.close()


app = FastAPI(title="江湖图谱 API", lifespan=lifespan)
app.include_router(auth_router)
app.include_router(ontology_router)
app.include_router(graph_router)
app.include_router(qa_router)
app.include_router(projects_router)
app.include_router(jobs_router)
app.include_router(extraction_router)
app.include_router(review_router)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
