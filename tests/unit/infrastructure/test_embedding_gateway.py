from pathlib import Path
from typing import Any

import pytest

from opercerta.infrastructure.embedding_gateway import (
    EMBEDDING_DIMENSION,
    EMBEDDING_MODEL,
    FastEmbedGateway,
)


class FakeEmbeddingModel:
    def __init__(self, vectors: list[list[float]]) -> None:
        self.vectors = vectors
        self.calls: list[tuple[list[str], int]] = []

    def embed(self, documents: list[str], batch_size: int = 256) -> list[list[float]]:
        self.calls.append((documents, batch_size))
        return self.vectors


@pytest.mark.asyncio
async def test_fixed_chinese_model_returns_immutable_512_vectors(tmp_path: Path) -> None:
    model = FakeEmbeddingModel([[0.0] * EMBEDDING_DIMENSION, [1.0] * EMBEDDING_DIMENSION])
    factory_calls: list[dict[str, Any]] = []

    def factory(**kwargs: Any) -> FakeEmbeddingModel:
        factory_calls.append(kwargs)
        return model

    gateway = FastEmbedGateway(tmp_path / "models", model_factory=factory)
    vectors = await gateway.embed_documents(("库存补货", "设备维修"))

    assert gateway.model_id == EMBEDDING_MODEL
    assert gateway.dimension == 512
    assert len(vectors) == 2
    assert all(isinstance(vector, tuple) and len(vector) == 512 for vector in vectors)
    assert factory_calls == [
        {
            "model_name": EMBEDDING_MODEL,
            "cache_dir": str(tmp_path / "models"),
            "lazy_load": True,
        }
    ]
    assert model.calls == [(["库存补货", "设备维修"], 32)]


@pytest.mark.asyncio
async def test_invalid_provider_dimension_fails_closed(tmp_path: Path) -> None:
    model = FakeEmbeddingModel([[0.0] * 511])
    gateway = FastEmbedGateway(tmp_path, model_factory=lambda **_: model)

    with pytest.raises(ValueError, match="embedding_dimension_mismatch"):
        await gateway.embed_documents(("库存补货",))


@pytest.mark.asyncio
async def test_empty_or_oversized_input_is_rejected_before_model_call(tmp_path: Path) -> None:
    model = FakeEmbeddingModel([])
    gateway = FastEmbedGateway(tmp_path, model_factory=lambda **_: model)

    for texts in ((), ("   ",), ("x" * 4_001,)):
        with pytest.raises(ValueError, match="embedding_input_invalid"):
            await gateway.embed_documents(texts)
    assert model.calls == []


@pytest.mark.asyncio
async def test_wrong_result_count_fails_closed(tmp_path: Path) -> None:
    model = FakeEmbeddingModel([[0.0] * 512])
    gateway = FastEmbedGateway(tmp_path, model_factory=lambda **_: model)

    with pytest.raises(ValueError, match="embedding_result_count_mismatch"):
        await gateway.embed_documents(("库存", "审批"))
