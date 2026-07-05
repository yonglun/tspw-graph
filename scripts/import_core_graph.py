#!/usr/bin/env python3
import argparse
import hashlib
import sys
from pathlib import Path

from sqlalchemy import create_engine

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/api/src"))

from app.graph.importer import GraphImporter
from app.graph.models import GraphDocument
from app.graph.neo4j import Neo4jGraphWriter
from app.projects.repository import ProjectRepository
from app.settings import get_settings

DEFAULT_DOCUMENT = ROOT / "data/xiaoao/core-graph.json"
DEFAULT_SOURCE = ROOT / "笑傲江湖/笑傲江湖.txt"


def load_and_validate(document_path: Path, source_path: Path) -> GraphDocument:
    document = GraphDocument.model_validate_json(document_path.read_text())
    source = source_path.read_text()
    for evidence in document.evidence:
        actual = source[evidence.start_offset : evidence.end_offset]
        if actual != evidence.quote:
            raise ValueError(f"evidence offset mismatch: {evidence.id}")
        digest = hashlib.sha256(evidence.quote.encode()).hexdigest()
        if digest != evidence.text_hash:
            raise ValueError(f"evidence hash mismatch: {evidence.id}")
    return document


def main() -> int:
    parser = argparse.ArgumentParser(description="Import the curated Xiaoao graph")
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--document", type=Path, default=DEFAULT_DOCUMENT)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    args = parser.parse_args()

    document = load_and_validate(args.document, args.source)
    if args.validate_only:
        print(
            f"validated entities={len(document.entities)} "
            f"facts={len(document.facts)} evidence={len(document.evidence)}"
        )
        return 0

    settings = get_settings()
    ProjectRepository(create_engine(settings.sqlite_url)).ensure_builtin_project(
        document.project.id, document.project.title
    )
    writer = Neo4jGraphWriter.from_settings(settings)
    try:
        summary = GraphImporter(writer).import_document(document)
    finally:
        writer.close()
    print(
        f"created_entities={summary.created_entities} "
        f"created_facts={summary.created_facts} "
        f"created_evidence={summary.created_evidence}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
