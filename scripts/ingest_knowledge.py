"""Validate or ingest OperCerta's versioned synthetic Chinese SOP assets."""

import argparse
import asyncio
import json
import os
from hashlib import sha256
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from opercerta.domain.knowledge import build_knowledge_ingest_command
from opercerta.domain.scenarios import ScenarioKind
from opercerta.infrastructure.db.knowledge_repository import KnowledgeRepository
from opercerta.infrastructure.embedding_gateway import (
    EMBEDDING_DIMENSION,
    EMBEDDING_MODEL,
    FastEmbedGateway,
)

ROOT = Path(__file__).resolve().parents[1]
SafeSlug = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=128,
        pattern=r"^[a-z][a-z0-9-]*$",
    ),
]
Version = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=64,
        pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$",
    ),
]
Digest = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]


class StrictManifestModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class EmbeddingManifest(StrictManifestModel):
    model: Literal["BAAI/bge-small-zh-v1.5"]
    dimension: Literal[512]


class ChunkingManifest(StrictManifestModel):
    strategy: Literal["markdown_h2"]
    max_chars: Literal[4000]


class DocumentManifest(StrictManifestModel):
    scenario: ScenarioKind
    slug: SafeSlug
    version: Version
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    path: Annotated[str, StringConstraints(pattern=r"^[a-z0-9-]+\.md$")]
    sha256: Digest
    active: Literal[True]
    synthetic: Literal[True]


class KnowledgeManifest(StrictManifestModel):
    schema_version: Literal[1]
    embedding: EmbeddingManifest
    chunking: ChunkingManifest
    documents: Annotated[tuple[DocumentManifest, ...], Field(min_length=3, max_length=3)]


class KnowledgeAssetReport(StrictManifestModel):
    embedding_model: str
    embedding_dimension: int
    document_count: int
    chunk_count: int
    scenarios: tuple[str, ...]


class SourceChunk(StrictManifestModel):
    content: str
    section: str


def load_manifest(root: Path) -> KnowledgeManifest:
    path = root / "data" / "knowledge" / "manifest.json"
    return KnowledgeManifest.model_validate_json(path.read_text(encoding="utf-8"))


def chunk_markdown(text: str, *, max_chars: int = 4_000) -> tuple[SourceChunk, ...]:
    sections: list[SourceChunk] = []
    heading: str | None = None
    lines: list[str] = []

    def append_section() -> None:
        if heading is None:
            return
        content = "\n".join(lines).strip()
        combined = f"## {heading}\n\n{content}" if content else f"## {heading}"
        if len(combined) > max_chars:
            raise ValueError("knowledge_chunk_too_large")
        sections.append(SourceChunk(content=combined, section=heading))

    for raw_line in text.splitlines():
        if raw_line.startswith("## "):
            append_section()
            heading = raw_line.removeprefix("## ").strip()
            lines = []
        elif heading is not None:
            lines.append(raw_line)
    append_section()
    if not sections:
        raise ValueError("knowledge_source_has_no_h2_sections")
    if len({section.content for section in sections}) != len(sections):
        raise ValueError("knowledge_source_has_duplicate_chunks")
    return tuple(sections)


def _validated_sources(
    root: Path,
    manifest: KnowledgeManifest,
) -> tuple[tuple[DocumentManifest, tuple[SourceChunk, ...]], ...]:
    knowledge_root = (root / "data" / "knowledge").resolve()
    validated = []
    for document in manifest.documents:
        source_path = (knowledge_root / document.path).resolve()
        if source_path.parent != knowledge_root or not source_path.is_file():
            raise ValueError("knowledge_source_path_invalid")
        raw = source_path.read_bytes()
        if sha256(raw).hexdigest() != document.sha256:
            raise ValueError("knowledge_source_checksum_mismatch")
        text = raw.decode("utf-8")
        if "合成" not in text or "不" not in text:
            raise ValueError("knowledge_source_disclaimer_missing")
        chunks = chunk_markdown(text, max_chars=manifest.chunking.max_chars)
        validated.append((document, chunks))
    scenarios = {document.scenario for document, _ in validated}
    if scenarios != set(ScenarioKind):
        raise ValueError("knowledge_scenarios_incomplete")
    return tuple(validated)


def check_knowledge_assets(root: Path = ROOT) -> KnowledgeAssetReport:
    manifest = load_manifest(root)
    if (
        manifest.embedding.model != EMBEDDING_MODEL
        or manifest.embedding.dimension != EMBEDDING_DIMENSION
    ):
        raise ValueError("knowledge_embedding_contract_mismatch")
    sources = _validated_sources(root, manifest)
    return KnowledgeAssetReport(
        embedding_model=manifest.embedding.model,
        embedding_dimension=manifest.embedding.dimension,
        document_count=len(sources),
        chunk_count=sum(len(chunks) for _, chunks in sources),
        scenarios=tuple(sorted(document.scenario.value for document, _ in sources)),
    )


async def ingest_knowledge(root: Path, cache_dir: Path) -> list[dict[str, object]]:
    database_url = os.environ.get("OPERCERTA_DATABASE_URL")
    if not database_url:
        raise ValueError("OPERCERTA_DATABASE_URL is required")
    manifest = load_manifest(root)
    sources = _validated_sources(root, manifest)
    gateway = FastEmbedGateway(cache_dir)
    parsed_url = make_url(database_url)
    original_pgpassword = os.environ.get("PGPASSWORD")
    if parsed_url.password is not None:
        os.environ["PGPASSWORD"] = parsed_url.password
    engine = create_async_engine(parsed_url.set(password=None), pool_pre_ping=True)
    summaries: list[dict[str, object]] = []
    try:
        repository = KnowledgeRepository(engine)
        for document, chunks in sources:
            vectors = await gateway.embed_documents(tuple(chunk.content for chunk in chunks))
            result = await repository.ingest(
                build_knowledge_ingest_command(
                    scenario=document.scenario,
                    slug=document.slug,
                    version=document.version,
                    title=document.title,
                    active=document.active,
                    chunks=tuple(
                        (
                            chunk.content,
                            vector,
                            {
                                "section": chunk.section,
                                "source_path": document.path,
                                "source_sha256": document.sha256,
                                "synthetic": True,
                            },
                        )
                        for chunk, vector in zip(chunks, vectors, strict=True)
                    ),
                )
            )
            summaries.append(
                {
                    "scenario": document.scenario.value,
                    "slug": document.slug,
                    "version": document.version,
                    "document_id": str(result.document.id),
                    "chunks": len(result.chunks),
                    "replayed": result.replayed,
                }
            )
    finally:
        await engine.dispose()
        if original_pgpassword is None:
            os.environ.pop("PGPASSWORD", None)
        else:
            os.environ["PGPASSWORD"] = original_pgpassword
    return summaries


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=Path.home() / ".cache" / "opercerta" / "fastembed",
    )
    args = parser.parse_args()
    if args.check:
        payload: object = check_knowledge_assets(args.root).model_dump(mode="json")
    else:
        payload = asyncio.run(ingest_knowledge(args.root, args.cache_dir))
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
