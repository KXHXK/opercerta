import asyncio
from uuid import UUID

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncEngine

from opercerta.domain.errors import KnowledgeVersionConflict
from opercerta.domain.knowledge import (
    KnowledgeSearchQuery,
    build_knowledge_ingest_command,
)
from opercerta.domain.scenarios import ScenarioKind
from opercerta.infrastructure.db.knowledge_repository import KnowledgeRepository
from opercerta.infrastructure.db.schema import knowledge_chunks, knowledge_documents


def embedding(axis: int) -> tuple[float, ...]:
    values = [0.0] * 512
    values[axis] = 1.0
    return tuple(values)


def command(
    *,
    scenario: ScenarioKind = ScenarioKind.INVENTORY,
    version: str = "1.0.0",
    title: str = "库存补货审批 SOP",
    content: str = "库存低于补货点时需核对可用量和审批绑定。",
    vector: tuple[float, ...] | None = None,
    active: bool = True,
):
    return build_knowledge_ingest_command(
        scenario=scenario,
        slug="controlled-action-sop",
        version=version,
        title=title,
        active=active,
        chunks=((content, vector or embedding(0), {"section": "approval"}),),
    )


async def cleanup_knowledge(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.execute(delete(knowledge_documents))


@pytest.mark.asyncio
async def test_identical_ingest_replays_without_duplicate_documents_or_chunks(
    engine: AsyncEngine,
) -> None:
    repository = KnowledgeRepository(engine)

    try:
        first = await repository.ingest(command())
        replay = await repository.ingest(command())

        assert first.replayed is False
        assert replay.replayed is True
        assert replay.document.id == first.document.id
        assert replay.chunks == first.chunks
        async with engine.connect() as connection:
            document_count = int(
                await connection.scalar(select(func.count()).select_from(knowledge_documents)) or 0
            )
            chunk_count = int(
                await connection.scalar(select(func.count()).select_from(knowledge_chunks)) or 0
            )
        assert document_count == 1
        assert chunk_count == 1
    finally:
        await cleanup_knowledge(engine)


@pytest.mark.asyncio
async def test_active_version_and_scenario_filters_prevent_cross_scenario_leakage(
    engine: AsyncEngine,
) -> None:
    repository = KnowledgeRepository(engine)

    try:
        inventory_v1 = await repository.ingest(command(version="1.0.0", active=False))
        inventory_v2 = await repository.ingest(
            command(
                version="2.0.0",
                content="补货前必须重新获取库存事实。批准后不得复用缓存。",
                vector=embedding(1),
            )
        )
        equipment = await repository.ingest(
            command(
                scenario=ScenarioKind.EQUIPMENT,
                version="9.0.0",
                title="设备维修 SOP",
                content="设备维修前核对告警等级。",
                vector=embedding(0),
            )
        )

        active_inventory = await repository.search(
            KnowledgeSearchQuery(
                scenario=ScenarioKind.INVENTORY,
                query_embedding=embedding(0),
                limit=5,
            )
        )
        historical_inventory = await repository.search(
            KnowledgeSearchQuery(
                scenario=ScenarioKind.INVENTORY,
                query_embedding=embedding(0),
                version="1.0.0",
                active_only=False,
                limit=5,
            )
        )

        assert [result.document_id for result in active_inventory] == [inventory_v2.document.id]
        assert equipment.document.id not in {result.document_id for result in active_inventory}
        assert [result.document_id for result in historical_inventory] == [inventory_v1.document.id]
    finally:
        await cleanup_knowledge(engine)


@pytest.mark.asyncio
async def test_search_orders_fixed_vectors_by_cosine_similarity(engine: AsyncEngine) -> None:
    repository = KnowledgeRepository(engine)

    try:
        exact = await repository.ingest(command(version="1.0.0", vector=embedding(0)))
        orthogonal = await repository.ingest(command(version="2.0.0", vector=embedding(1)))

        results = await repository.search(
            KnowledgeSearchQuery(
                scenario=ScenarioKind.INVENTORY,
                query_embedding=embedding(0),
                active_only=False,
                limit=5,
            )
        )

        assert [result.document_id for result in results] == [
            exact.document.id,
            orthogonal.document.id,
        ]
        assert results[0].score > results[1].score
        assert results[0].score == pytest.approx(1.0)
    finally:
        await cleanup_knowledge(engine)


@pytest.mark.asyncio
async def test_missing_document_activation_changes_nothing(engine: AsyncEngine) -> None:
    repository = KnowledgeRepository(engine)

    try:
        assert (
            await repository.activate_version(
                ScenarioKind.TASK,
                "controlled-action-sop",
                "404.0.0",
            )
            is False
        )
        async with engine.connect() as connection:
            assert (
                int(
                    await connection.scalar(select(func.count()).select_from(knowledge_documents))
                    or 0
                )
                == 0
            )
    finally:
        await cleanup_knowledge(engine)


@pytest.mark.asyncio
async def test_document_ids_are_real_uuid_values(engine: AsyncEngine) -> None:
    repository = KnowledgeRepository(engine)

    try:
        result = await repository.ingest(command())
        assert isinstance(result.document.id, UUID)
        assert all(isinstance(chunk.id, UUID) for chunk in result.chunks)
    finally:
        await cleanup_knowledge(engine)


@pytest.mark.asyncio
async def test_same_version_with_changed_content_fails_without_mutation(
    engine: AsyncEngine,
) -> None:
    repository = KnowledgeRepository(engine)

    try:
        original = await repository.ingest(command())
        with pytest.raises(KnowledgeVersionConflict):
            await repository.ingest(command(content="同一版本不得悄悄替换为不同的 SOP 内容。"))
        async with engine.connect() as connection:
            documents = int(
                await connection.scalar(select(func.count()).select_from(knowledge_documents)) or 0
            )
            chunks = int(
                await connection.scalar(select(func.count()).select_from(knowledge_chunks)) or 0
            )
        assert original.replayed is False
        assert (documents, chunks) == (1, 1)
    finally:
        await cleanup_knowledge(engine)


@pytest.mark.asyncio
async def test_concurrent_identical_ingest_creates_one_document(engine: AsyncEngine) -> None:
    repository = KnowledgeRepository(engine)

    try:
        results = await asyncio.gather(*[repository.ingest(command()) for _ in range(10)])
        assert sum(not result.replayed for result in results) == 1
        assert len({result.document.id for result in results}) == 1
        async with engine.connect() as connection:
            assert (
                int(
                    await connection.scalar(select(func.count()).select_from(knowledge_documents))
                    or 0
                )
                == 1
            )
    finally:
        await cleanup_knowledge(engine)


@pytest.mark.asyncio
async def test_activate_version_deprecates_previous_version(engine: AsyncEngine) -> None:
    repository = KnowledgeRepository(engine)

    try:
        first = await repository.ingest(command(version="1.0.0", active=True))
        second = await repository.ingest(command(version="2.0.0", active=False))
        assert await repository.activate_version(
            ScenarioKind.INVENTORY,
            "controlled-action-sop",
            "2.0.0",
        )

        results = await repository.search(
            KnowledgeSearchQuery(
                scenario=ScenarioKind.INVENTORY,
                query_embedding=embedding(0),
                limit=5,
            )
        )
        assert [result.document_id for result in results] == [second.document.id]
        assert first.document.id not in {result.document_id for result in results}
    finally:
        await cleanup_knowledge(engine)
