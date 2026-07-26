from datetime import UTC, datetime
from typing import cast
from uuid import uuid4

from pydantic import JsonValue
from sqlalchemy import RowMapping, Select, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from opercerta.domain.errors import KnowledgeVersionConflict
from opercerta.domain.knowledge import (
    KnowledgeChunkRecord,
    KnowledgeDocumentRecord,
    KnowledgeIngestCommand,
    KnowledgeIngestResult,
    KnowledgeSearchQuery,
    KnowledgeSearchResult,
)
from opercerta.domain.scenarios import ScenarioKind
from opercerta.infrastructure.db.schema import knowledge_chunks, knowledge_documents


class KnowledgeRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def ingest(self, command: KnowledgeIngestCommand) -> KnowledgeIngestResult:
        async with self._engine.begin() as connection:
            created_at = datetime.now(UTC)
            document_id = (
                await connection.execute(
                    insert(knowledge_documents)
                    .values(
                        id=uuid4(),
                        scenario=command.scenario.value,
                        slug=command.slug,
                        version=command.version,
                        title=command.title,
                        checksum=command.checksum,
                        active=command.active,
                        created_at=created_at,
                        updated_at=created_at,
                    )
                    .on_conflict_do_nothing(
                        constraint="uq_knowledge_documents_scenario_slug_version"
                    )
                    .returning(knowledge_documents.c.id)
                )
            ).scalar_one_or_none()
            replayed = document_id is None
            if replayed:
                existing = await self._find_document(connection, command)
                self._require_same_document(existing, command)
                document_id = existing["id"]
            else:
                await connection.execute(
                    insert(knowledge_chunks),
                    [
                        {
                            "id": uuid4(),
                            "document_id": document_id,
                            "chunk_index": chunk.chunk_index,
                            "content": chunk.content,
                            "content_hash": chunk.content_hash,
                            "embedding": list(chunk.embedding),
                            "metadata": chunk.metadata,
                            "created_at": created_at,
                        }
                        for chunk in command.chunks
                    ],
                )

            document = await self._find_document(connection, command)
            chunks = await self._find_chunks(connection, document_id)
            self._require_same_chunks(chunks, command)

        return KnowledgeIngestResult(
            document=self._document_record(document),
            chunks=tuple(self._chunk_record(row) for row in chunks),
            replayed=replayed,
        )

    async def activate_version(
        self,
        scenario: ScenarioKind,
        slug: str,
        version: str,
    ) -> bool:
        async with self._engine.begin() as connection:
            target_id = (
                await connection.execute(
                    select(knowledge_documents.c.id)
                    .where(
                        knowledge_documents.c.scenario == scenario.value,
                        knowledge_documents.c.slug == slug,
                        knowledge_documents.c.version == version,
                    )
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if target_id is None:
                return False
            changed_at = datetime.now(UTC)
            await connection.execute(
                update(knowledge_documents)
                .where(
                    knowledge_documents.c.scenario == scenario.value,
                    knowledge_documents.c.slug == slug,
                )
                .values(active=False, updated_at=changed_at)
            )
            await connection.execute(
                update(knowledge_documents)
                .where(knowledge_documents.c.id == target_id)
                .values(active=True, updated_at=changed_at)
            )
        return True

    async def search(
        self,
        query: KnowledgeSearchQuery,
    ) -> tuple[KnowledgeSearchResult, ...]:
        distance = knowledge_chunks.c.embedding.cosine_distance(list(query.query_embedding))
        statement: Select[tuple[object, ...]] = (
            select(
                knowledge_documents.c.id.label("document_id"),
                knowledge_chunks.c.id.label("chunk_id"),
                knowledge_documents.c.scenario,
                knowledge_documents.c.slug,
                knowledge_documents.c.version,
                knowledge_documents.c.title,
                knowledge_chunks.c.chunk_index,
                knowledge_chunks.c.content,
                knowledge_chunks.c.metadata,
                (1 - distance).label("score"),
            )
            .select_from(
                knowledge_chunks.join(
                    knowledge_documents,
                    knowledge_chunks.c.document_id == knowledge_documents.c.id,
                )
            )
            .where(knowledge_documents.c.scenario == query.scenario.value)
            .order_by(distance, knowledge_documents.c.version, knowledge_chunks.c.chunk_index)
            .limit(query.limit)
        )
        if query.active_only:
            statement = statement.where(knowledge_documents.c.active.is_(True))
        if query.version is not None:
            statement = statement.where(knowledge_documents.c.version == query.version)

        async with self._engine.connect() as connection:
            rows = (await connection.execute(statement)).mappings().all()
        return tuple(self._search_result(row) for row in rows)

    async def _find_document(
        self,
        connection: AsyncConnection,
        command: KnowledgeIngestCommand,
    ) -> RowMapping:
        return (
            (
                await connection.execute(
                    select(knowledge_documents).where(
                        knowledge_documents.c.scenario == command.scenario.value,
                        knowledge_documents.c.slug == command.slug,
                        knowledge_documents.c.version == command.version,
                    )
                )
            )
            .mappings()
            .one()
        )

    async def _find_chunks(
        self,
        connection: AsyncConnection,
        document_id: object,
    ) -> list[RowMapping]:
        return list(
            (
                await connection.execute(
                    select(knowledge_chunks)
                    .where(knowledge_chunks.c.document_id == document_id)
                    .order_by(knowledge_chunks.c.chunk_index)
                )
            )
            .mappings()
            .all()
        )

    def _require_same_document(
        self,
        row: RowMapping,
        command: KnowledgeIngestCommand,
    ) -> None:
        if (
            row["checksum"] != command.checksum
            or row["title"] != command.title
            or bool(row["active"]) is not command.active
        ):
            raise KnowledgeVersionConflict

    def _require_same_chunks(
        self,
        rows: list[RowMapping],
        command: KnowledgeIngestCommand,
    ) -> None:
        stored = tuple(
            (
                int(row["chunk_index"]),
                str(row["content"]),
                str(row["content_hash"]),
                cast(dict[str, JsonValue], row["metadata"]),
            )
            for row in rows
        )
        expected = tuple(
            (chunk.chunk_index, chunk.content, chunk.content_hash, chunk.metadata)
            for chunk in command.chunks
        )
        if stored != expected:
            raise KnowledgeVersionConflict

    def _document_record(self, row: RowMapping) -> KnowledgeDocumentRecord:
        return KnowledgeDocumentRecord(
            id=row["id"],
            scenario=row["scenario"],
            slug=row["slug"],
            version=row["version"],
            title=row["title"],
            checksum=row["checksum"],
            active=row["active"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _chunk_record(self, row: RowMapping) -> KnowledgeChunkRecord:
        return KnowledgeChunkRecord(
            id=row["id"],
            document_id=row["document_id"],
            chunk_index=row["chunk_index"],
            content=row["content"],
            content_hash=row["content_hash"],
            metadata=row["metadata"],
            created_at=row["created_at"],
        )

    def _search_result(self, row: RowMapping) -> KnowledgeSearchResult:
        return KnowledgeSearchResult(
            document_id=row["document_id"],
            chunk_id=row["chunk_id"],
            scenario=row["scenario"],
            slug=row["slug"],
            version=row["version"],
            title=row["title"],
            chunk_index=row["chunk_index"],
            content=row["content"],
            metadata=row["metadata"],
            score=float(row["score"]),
        )
