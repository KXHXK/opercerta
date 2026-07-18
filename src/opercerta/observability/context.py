from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from uuid import uuid4

_REQUEST_ID: ContextVar[str | None] = ContextVar(
    "opercerta_request_id",
    default=None,
)


def new_request_id() -> str:
    return str(uuid4())


def current_request_id() -> str | None:
    return _REQUEST_ID.get()


@contextmanager
def request_context(request_id: str) -> Iterator[None]:
    token = _REQUEST_ID.set(request_id)
    try:
        yield
    finally:
        _REQUEST_ID.reset(token)
