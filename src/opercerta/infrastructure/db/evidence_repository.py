import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID, uuid4

from pydantic import JsonValue
from sqlalchemy import case, insert, select
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from opercerta.domain.errors import EvidenceConflict, OperationNotFound
from opercerta.domain.replenishment import EvidenceBundle
from opercerta.domain.work_orders import canonical_payload_json
from opercerta.infrastructure.db.schema import evidence, operations


@dataclass(frozen=True, slots=True)
class EvidenceRecord:
    id: UUID
    operation_id: UUID
    evidence_id: UUID
    evidence_type: str
    source_tool: str
    source_version: str
    captured_at: datetime
    expires_at: datetime
    content: dict[str, JsonValue]
    content_hash: str
    created_at: datetime


def hash_json(content: dict[str, JsonValue]) -> str:
    canonical_json = canonical_payload_json(content)
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


class EvidenceRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def save_bundle(
        self,
        operation_id: UUID,
        bundle: EvidenceBundle,
    ) -> tuple[EvidenceRecord, EvidenceRecord]:
        return await self._save(operation_id, bundle)

    async def save_refresh(
        self,
        operation_id: UUID,
        bundle: EvidenceBundle,
    ) -> tuple[EvidenceRecord, EvidenceRecord]:
        return await self._save(operation_id, bundle)

    async def list_for_operation(self, operation_id: UUID) -> list[EvidenceRecord]:
        async with self._engine.connect() as connection:
            rows = (
                (
                    await connection.execute(
                        select(evidence)
                        .where(evidence.c.operation_id == operation_id)
                        .order_by(
                            evidence.c.created_at,
                            case(
                                (evidence.c.evidence_type == "inventory", 0),
                                (evidence.c.evidence_type == "policy", 1),
                                else_=2,
                            ),
                            evidence.c.id,
                        )
                    )
                )
                .mappings()
                .all()
            )
        return [self._record(row) for row in rows]

    async def _save(
        self,
        operation_id: UUID,
        bundle: EvidenceBundle,
    ) -> tuple[EvidenceRecord, EvidenceRecord]:
        async with self._engine.begin() as connection:
            await self._lock_operation(connection, operation_id)
            return await self._save_in_connection(connection, operation_id, bundle)

    async def _save_in_connection(
        self,
        connection: AsyncConnection,
        operation_id: UUID,
        bundle: EvidenceBundle,
    ) -> tuple[EvidenceRecord, EvidenceRecord]:
        specifications = self._specifications(bundle)
        existing_rows = (
            (
                await connection.execute(
                    select(evidence).where(
                        evidence.c.operation_id == operation_id,
                        evidence.c.evidence_id.in_(
                            [specification["evidence_id"] for specification in specifications]
                        ),
                    )
                )
            )
            .mappings()
            .all()
        )
        existing = {cast(UUID, row["evidence_id"]): row for row in existing_rows}
        records: list[EvidenceRecord] = []
        created_at = datetime.now(UTC)
        for specification in specifications:
            evidence_id = cast(UUID, specification["evidence_id"])
            row = existing.get(evidence_id)
            if row is not None:
                if not self._matches(row, specification):
                    raise EvidenceConflict
                records.append(self._record(row))
                continue

            record_id = uuid4()
            await connection.execute(
                insert(evidence).values(
                    id=record_id,
                    operation_id=operation_id,
                    created_at=created_at,
                    **specification,
                )
            )
            records.append(
                EvidenceRecord(
                    id=record_id,
                    operation_id=operation_id,
                    created_at=created_at,
                    evidence_id=evidence_id,
                    evidence_type=cast(str, specification["evidence_type"]),
                    source_tool=cast(str, specification["source_tool"]),
                    source_version=cast(str, specification["source_version"]),
                    captured_at=cast(datetime, specification["captured_at"]),
                    expires_at=cast(datetime, specification["expires_at"]),
                    content=self._copy_content(
                        cast(dict[str, JsonValue], specification["content"])
                    ),
                    content_hash=cast(str, specification["content_hash"]),
                )
            )
        return cast(tuple[EvidenceRecord, EvidenceRecord], tuple(records))

    async def _lock_operation(
        self,
        connection: AsyncConnection,
        operation_id: UUID,
    ) -> None:
        found = (
            await connection.execute(
                select(operations.c.id).where(operations.c.id == operation_id).with_for_update()
            )
        ).scalar_one_or_none()
        if found is None:
            raise OperationNotFound(operation_id)

    def _specifications(self, bundle: EvidenceBundle) -> tuple[dict[str, object], ...]:
        ttl = timedelta(seconds=bundle.policy.evidence_ttl_seconds)
        inventory_content = cast(
            dict[str, JsonValue],
            bundle.inventory.model_dump(mode="json"),
        )
        policy_content = cast(
            dict[str, JsonValue],
            bundle.policy.model_dump(mode="json"),
        )
        return (
            {
                "evidence_id": bundle.inventory.evidence_id,
                "evidence_type": "inventory",
                "source_tool": "inventory",
                "source_version": bundle.inventory.source_version,
                "captured_at": bundle.inventory.captured_at,
                "expires_at": bundle.inventory.captured_at + ttl,
                "content": inventory_content,
                "content_hash": hash_json(inventory_content),
            },
            {
                "evidence_id": bundle.policy.evidence_id,
                "evidence_type": "policy",
                "source_tool": "policy",
                "source_version": bundle.policy.rule_version,
                "captured_at": bundle.policy.captured_at,
                "expires_at": bundle.policy.captured_at + ttl,
                "content": policy_content,
                "content_hash": hash_json(policy_content),
            },
        )

    def _matches(self, row: RowMapping, specification: dict[str, object]) -> bool:
        return (
            all(row[key] == value for key, value in specification.items() if key != "content")
            and cast(dict[str, JsonValue], row["content"]) == specification["content"]
        )

    def _record(self, row: RowMapping) -> EvidenceRecord:
        return EvidenceRecord(
            id=cast(UUID, row["id"]),
            operation_id=cast(UUID, row["operation_id"]),
            evidence_id=cast(UUID, row["evidence_id"]),
            evidence_type=str(row["evidence_type"]),
            source_tool=str(row["source_tool"]),
            source_version=str(row["source_version"]),
            captured_at=cast(datetime, row["captured_at"]),
            expires_at=cast(datetime, row["expires_at"]),
            content=self._copy_content(cast(dict[str, JsonValue], row["content"])),
            content_hash=str(row["content_hash"]),
            created_at=cast(datetime, row["created_at"]),
        )

    def _copy_content(self, content: dict[str, JsonValue]) -> dict[str, JsonValue]:
        return cast(
            dict[str, JsonValue],
            json.loads(canonical_payload_json(content)),
        )
