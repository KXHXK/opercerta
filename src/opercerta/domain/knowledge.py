from datetime import datetime
from hashlib import sha256
from json import dumps
from typing import Annotated, Literal, Protocol
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    FiniteFloat,
    JsonValue,
    StrictBool,
    StringConstraints,
    field_validator,
    model_validator,
)

from opercerta.domain.scenarios import Digest, ScenarioKind, Version

KnowledgeSlug = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=128,
        pattern=r"^[a-z][a-z0-9-]*$",
    ),
]
KnowledgeTitle = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=200),
]
ChunkContent = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=4_000),
]
ChunkIndex = Annotated[int, Field(strict=True, ge=0)]
SearchLimit = Annotated[int, Field(strict=True, ge=1, le=20)]


class StrictKnowledgeModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class KnowledgeChunkInput(StrictKnowledgeModel):
    chunk_index: ChunkIndex
    content: ChunkContent
    content_hash: Digest
    embedding: tuple[FiniteFloat, ...]
    metadata: dict[str, JsonValue]

    @field_validator("embedding")
    @classmethod
    def require_embedding_dimension(cls, value: tuple[float, ...]) -> tuple[float, ...]:
        if len(value) != 512:
            raise ValueError("knowledge embedding must have 512 dimensions")
        return value

    @model_validator(mode="after")
    def require_matching_content_hash(self) -> "KnowledgeChunkInput":
        expected = sha256(self.content.encode("utf-8")).hexdigest()
        if self.content_hash != expected:
            raise ValueError("knowledge content hash mismatch")
        return self


class KnowledgeIngestCommand(StrictKnowledgeModel):
    scenario: ScenarioKind
    slug: KnowledgeSlug
    version: Version
    title: KnowledgeTitle
    checksum: Digest
    active: StrictBool
    chunks: tuple[KnowledgeChunkInput, ...]

    @model_validator(mode="after")
    def require_valid_document(self) -> "KnowledgeIngestCommand":
        if not self.chunks:
            raise ValueError("knowledge document requires at least one chunk")
        indexes = tuple(chunk.chunk_index for chunk in self.chunks)
        if indexes != tuple(range(len(self.chunks))):
            raise ValueError("knowledge chunk indexes must be contiguous from zero")
        content_hashes = [chunk.content_hash for chunk in self.chunks]
        if len(content_hashes) != len(set(content_hashes)):
            raise ValueError("knowledge document contains duplicate chunks")
        if self.checksum != document_checksum(self.chunks):
            raise ValueError("knowledge document checksum mismatch")
        return self


class KnowledgeDocumentRecord(StrictKnowledgeModel):
    id: UUID
    scenario: ScenarioKind
    slug: KnowledgeSlug
    version: Version
    title: KnowledgeTitle
    checksum: Digest
    active: StrictBool
    created_at: datetime
    updated_at: datetime


class KnowledgeChunkRecord(StrictKnowledgeModel):
    id: UUID
    document_id: UUID
    chunk_index: ChunkIndex
    content: ChunkContent
    content_hash: Digest
    metadata: dict[str, JsonValue]
    created_at: datetime


class KnowledgeIngestResult(StrictKnowledgeModel):
    document: KnowledgeDocumentRecord
    chunks: tuple[KnowledgeChunkRecord, ...]
    replayed: StrictBool


class KnowledgeSearchQuery(StrictKnowledgeModel):
    scenario: ScenarioKind
    query_embedding: tuple[FiniteFloat, ...]
    version: Version | None = None
    active_only: StrictBool = True
    limit: SearchLimit = 5

    @field_validator("query_embedding")
    @classmethod
    def require_embedding_dimension(cls, value: tuple[float, ...]) -> tuple[float, ...]:
        if len(value) != 512:
            raise ValueError("knowledge query embedding must have 512 dimensions")
        return value


class KnowledgeSearchResult(StrictKnowledgeModel):
    document_id: UUID
    chunk_id: UUID
    scenario: ScenarioKind
    slug: KnowledgeSlug
    version: Version
    title: KnowledgeTitle
    chunk_index: ChunkIndex
    content: ChunkContent
    metadata: dict[str, JsonValue]
    score: FiniteFloat


class KnowledgeSearchEvidence(StrictKnowledgeModel):
    evidence_id: UUID
    scenario: ScenarioKind
    query: ChunkContent
    embedding_model: KnowledgeTitle
    status: Literal["ok"] = "ok"
    results: tuple[KnowledgeSearchResult, ...]


class TextEmbeddingGateway(Protocol):
    model_id: str
    dimension: int

    async def embed_documents(
        self,
        texts: tuple[str, ...],
    ) -> tuple[tuple[float, ...], ...]: ...


def document_checksum(chunks: tuple[KnowledgeChunkInput, ...]) -> str:
    payload = [
        {
            "chunk_index": chunk.chunk_index,
            "content_hash": chunk.content_hash,
            "embedding": chunk.embedding,
            "metadata": chunk.metadata,
        }
        for chunk in chunks
    ]
    canonical = dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return sha256(canonical.encode("utf-8")).hexdigest()


def build_knowledge_ingest_command(
    *,
    scenario: ScenarioKind,
    slug: str,
    version: str,
    title: str,
    active: bool,
    chunks: tuple[tuple[str, tuple[float, ...], dict[str, JsonValue]], ...],
) -> KnowledgeIngestCommand:
    inputs = tuple(
        KnowledgeChunkInput(
            chunk_index=index,
            content=content,
            content_hash=sha256(content.strip().encode("utf-8")).hexdigest(),
            embedding=embedding,
            metadata=metadata,
        )
        for index, (content, embedding, metadata) in enumerate(chunks)
    )
    return KnowledgeIngestCommand(
        scenario=scenario,
        slug=slug,
        version=version,
        title=title,
        checksum=document_checksum(inputs),
        active=active,
        chunks=inputs,
    )
