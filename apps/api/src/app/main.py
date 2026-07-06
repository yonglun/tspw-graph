from fastapi import FastAPI

from app.graph.router import router as graph_router
from app.extraction.router import router as extraction_router
from app.jobs.router import router as jobs_router
from app.ontology.router import router as ontology_router
from app.projects.router import router as projects_router
from app.qa.router import router as qa_router

app = FastAPI(title="江湖图谱 API")
app.include_router(ontology_router)
app.include_router(graph_router)
app.include_router(qa_router)
app.include_router(projects_router)
app.include_router(jobs_router)
app.include_router(extraction_router)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
