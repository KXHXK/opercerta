import asyncio
from collections.abc import Callable, Iterable, Sequence
from math import isfinite
from pathlib import Path
from typing import Protocol, cast

from fastembed import TextEmbedding

EMBEDDING_MODEL = "BAAI/bge-small-zh-v1.5"
EMBEDDING_DIMENSION = 512
EMBEDDING_BATCH_SIZE = 32


class EmbeddingModel(Protocol):
    def embed(
        self,
        documents: list[str],
        batch_size: int = 256,
    ) -> Iterable[Sequence[float]]: ...


ModelFactory = Callable[..., EmbeddingModel]


class FastEmbedGateway:
    model_id = EMBEDDING_MODEL
    dimension = EMBEDDING_DIMENSION

    def __init__(
        self,
        cache_dir: Path,
        *,
        model_factory: ModelFactory | None = None,
    ) -> None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        factory = model_factory or cast(ModelFactory, TextEmbedding)
        self._model = factory(
            model_name=EMBEDDING_MODEL,
            cache_dir=str(cache_dir),
            lazy_load=True,
        )

    async def embed_documents(
        self,
        texts: tuple[str, ...],
    ) -> tuple[tuple[float, ...], ...]:
        normalized = self._validate_inputs(texts)
        raw = await asyncio.to_thread(
            lambda: list(
                self._model.embed(
                    list(normalized),
                    batch_size=EMBEDDING_BATCH_SIZE,
                )
            )
        )
        if len(raw) != len(normalized):
            raise ValueError("embedding_result_count_mismatch")
        vectors = tuple(tuple(float(value) for value in vector) for vector in raw)
        if any(
            len(vector) != EMBEDDING_DIMENSION or any(not isfinite(value) for value in vector)
            for vector in vectors
        ):
            raise ValueError("embedding_dimension_mismatch")
        return vectors

    def _validate_inputs(self, texts: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(text.strip() for text in texts)
        if (
            not normalized
            or any(not text or len(text) > 4_000 for text in normalized)
            or len(normalized) > 128
        ):
            raise ValueError("embedding_input_invalid")
        return normalized
