from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from alembic import command
from alembic.config import Config
from pydantic import SecretStr
from pytest import MonkeyPatch
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[3]
INVENTORY_EVIDENCE_ID = UUID("10000000-0000-4000-8000-000000000001")
POLICY_EVIDENCE_ID = UUID("20000000-0000-4000-8000-000000000002")


def test_three_business_migration_backfills_and_preserves_inventory_binding(
    database_url: SecretStr,
    monkeypatch: MonkeyPatch,
) -> None:
    parsed_url = make_url(database_url.get_secret_value())
    if parsed_url.password:
        monkeypatch.setenv("PGPASSWORD", parsed_url.password)
    passwordless_url = parsed_url.set(password=None)
    monkeypatch.setenv(
        "OPERCERTA_DATABASE_URL",
        passwordless_url.render_as_string(hide_password=False),
    )
    config = Config(str(ROOT / "alembic.ini"))
    engine = create_engine(passwordless_url)
    operation_id = uuid4()
    approval_id = uuid4()

    try:
        command.downgrade(config, "0002_inventory_replenishment")
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO operations (
                        id, thread_id, request_payload, status, next_audit_sequence
                    ) VALUES (
                        :id, :thread_id, CAST(:request_payload AS jsonb),
                        'resuming', 1
                    )
                    """
                ),
                {
                    "id": operation_id,
                    "thread_id": str(operation_id),
                    "request_payload": (
                        '{"message":"replenish","requested_action":'
                        '"create_work_order","object_type":"inventory",'
                        '"object_id":"SKU-LOW-001"}'
                    ),
                },
            )
            connection.execute(
                text(
                    """
                    INSERT INTO approvals (
                        id, operation_id, approver_id, decision, reason,
                        inventory_evidence_id, policy_evidence_id, rule_version,
                        decision_facts_hash, plan_hash, recommended_quantity,
                        created_at
                    ) VALUES (
                        :id, :operation_id, 'demo.approver', 'approved',
                        'historical synthetic decision', :inventory_evidence_id,
                        :policy_evidence_id, 'replenishment-v1', :facts_hash,
                        :plan_hash, 18, :created_at
                    )
                    """
                ),
                {
                    "id": approval_id,
                    "operation_id": operation_id,
                    "inventory_evidence_id": INVENTORY_EVIDENCE_ID,
                    "policy_evidence_id": POLICY_EVIDENCE_ID,
                    "facts_hash": "a" * 64,
                    "plan_hash": "b" * 64,
                    "created_at": datetime(2026, 7, 20, 8, 0, tzinfo=UTC),
                },
            )

        for _ in range(2):
            command.upgrade(config, "0003_three_business_operations")
            columns = {
                column["name"]
                for column in inspect(engine).get_columns("approvals", schema="public")
            }
            assert {"subject_evidence_id", "binding_payload"} <= columns
            with engine.connect() as connection:
                row = (
                    connection.execute(
                        text(
                            """
                            SELECT subject_evidence_id, binding_payload
                            FROM approvals WHERE id = :id
                            """
                        ),
                        {"id": approval_id},
                    )
                    .mappings()
                    .one()
                )
            assert row["subject_evidence_id"] == INVENTORY_EVIDENCE_ID
            assert row["binding_payload"] == {
                "scenario": "inventory",
                "subject_evidence_id": str(INVENTORY_EVIDENCE_ID),
                "policy_evidence_id": str(POLICY_EVIDENCE_ID),
                "rule_version": "replenishment-v1",
                "decision_facts_hash": "a" * 64,
                "plan_hash": "b" * 64,
                "parameters": {
                    "kind": "replenishment",
                    "recommended_quantity": 18,
                },
            }

            command.downgrade(config, "0002_inventory_replenishment")
            downgraded = {
                column["name"]
                for column in inspect(engine).get_columns("approvals", schema="public")
            }
            assert "subject_evidence_id" not in downgraded
            assert "binding_payload" not in downgraded
    finally:
        command.upgrade(config, "head")
        with engine.begin() as connection:
            connection.execute(
                text("DELETE FROM operations WHERE id = :id"),
                {"id": operation_id},
            )
        engine.dispose()
