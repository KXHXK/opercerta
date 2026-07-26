import math

import pytest
from pydantic import ValidationError

from opercerta.domain.knowledge import build_knowledge_ingest_command
from opercerta.domain.scenarios import ScenarioKind


def embedding(size: int = 512) -> tuple[float, ...]:
    return tuple(0.0 for _ in range(size))


@pytest.mark.parametrize("size", [0, 511, 513])
def test_embedding_dimension_is_exactly_512(size: int) -> None:
    with pytest.raises(ValidationError):
        build_knowledge_ingest_command(
            scenario=ScenarioKind.INVENTORY,
            slug="inventory-sop",
            version="1.0.0",
            title="库存 SOP",
            active=True,
            chunks=(("有效内容", embedding(size), {}),),
        )


@pytest.mark.parametrize("invalid", [math.nan, math.inf, -math.inf])
def test_embedding_rejects_non_finite_values(invalid: float) -> None:
    values = list(embedding())
    values[0] = invalid
    with pytest.raises(ValidationError):
        build_knowledge_ingest_command(
            scenario=ScenarioKind.INVENTORY,
            slug="inventory-sop",
            version="1.0.0",
            title="库存 SOP",
            active=True,
            chunks=(("有效内容", tuple(values), {}),),
        )


def test_document_requires_at_least_one_chunk() -> None:
    with pytest.raises(ValidationError):
        build_knowledge_ingest_command(
            scenario=ScenarioKind.INVENTORY,
            slug="inventory-sop",
            version="1.0.0",
            title="库存 SOP",
            active=True,
            chunks=(),
        )
