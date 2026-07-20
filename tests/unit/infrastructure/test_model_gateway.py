import json

import httpx
import pytest
from pydantic import SecretStr

from opercerta.domain.maintenance import MaintenanceAssessment
from opercerta.infrastructure.model_gateway import (
    ModelOutputInvalid,
    OpenAICompatibleModelGateway,
)


def maintenance_assessment() -> MaintenanceAssessment:
    return MaintenanceAssessment(
        equipment_id="EQ-PUMP-001",
        state="offline",
        alert_code="MOTOR_OVERHEAT",
        heartbeat_age_seconds=60,
        maintenance_required=True,
        reason="alert",
        priority="urgent",
        decision_facts_hash="a" * 64,
    )


def client_returning(content: dict[str, object]) -> httpx.AsyncClient:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer model-secret"
        payload = json.loads(request.content)
        assert payload["temperature"] == 0
        assert payload["max_tokens"] == 256
        assert payload["response_format"] == {"type": "json_object"}
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps(content)}}]},
        )

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def client_returning_sequence(
    contents: list[dict[str, object]],
) -> tuple[httpx.AsyncClient, list[int]]:
    calls: list[int] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        del request
        calls.append(1)
        content = contents[min(len(calls) - 1, len(contents) - 1)]
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps(content)}}]},
        )

    return httpx.AsyncClient(transport=httpx.MockTransport(handler)), calls


@pytest.mark.asyncio
async def test_real_model_accepts_only_explanation_fields() -> None:
    async with client_returning({"summary": "建议维修", "rationale": "存在严重告警"}) as client:
        gateway = OpenAICompatibleModelGateway(
            client=client,
            base_url="https://model.example/v1",
            model="interview-demo-model",
            api_key=SecretStr("model-secret"),
        )
        explanation = await gateway.explain_plan(maintenance_assessment())

    assert explanation.summary == "建议维修"
    assert explanation.rationale == "存在严重告警"


@pytest.mark.asyncio
async def test_real_model_rejects_authoritative_fields() -> None:
    async with client_returning(
        {"summary": "维修", "rationale": "告警", "priority": "low"}
    ) as client:
        gateway = OpenAICompatibleModelGateway(
            client=client,
            base_url="https://model.example/v1",
            model="interview-demo-model",
            api_key=SecretStr("model-secret"),
        )
        with pytest.raises(ModelOutputInvalid, match="model_output_invalid"):
            await gateway.explain_plan(maintenance_assessment())


@pytest.mark.asyncio
async def test_real_model_retries_invalid_output_once_then_accepts_strict_json() -> None:
    client, calls = client_returning_sequence(
        [
            {"summary": "repair", "rationale": "alert", "priority": "low"},
            {"summary": "repair", "rationale": "verified alert"},
        ]
    )
    async with client:
        gateway = OpenAICompatibleModelGateway(
            client=client,
            base_url="https://model.example/v1",
            model="interview-demo-model",
            api_key=SecretStr("model-secret"),
        )
        explanation = await gateway.explain_plan(maintenance_assessment())

    assert explanation.rationale == "verified alert"
    assert len(calls) == 2
