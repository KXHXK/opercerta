from enum import StrEnum
from hashlib import sha256
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from opercerta.domain.agent import SafeText
from opercerta.domain.scenarios import Digest, Version


class PromptId(StrEnum):
    PLANNER = "planner"
    TOOL_LOOP = "tool_loop"
    ANALYST = "analyst"
    VERIFIER = "verifier"
    REPORTER = "reporter"


class PromptSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    prompt_id: PromptId
    version: Version
    content_hash: Digest
    content: SafeText


_PROMPT_FILES: dict[PromptId, tuple[str, str]] = {
    PromptId.PLANNER: ("planner-v1.md", "v1"),
    PromptId.TOOL_LOOP: ("tool-loop-v1.md", "v1"),
    PromptId.ANALYST: ("analyst-v1.md", "v1"),
    PromptId.VERIFIER: ("verifier-v1.md", "v1"),
    PromptId.REPORTER: ("reporter-v1.md", "v1"),
}


class PromptRegistry:
    def __init__(self, root: Path) -> None:
        self._root = root

    @classmethod
    def packaged(cls) -> "PromptRegistry":
        return cls(Path(__file__).resolve().parents[1] / "prompts")

    def load(self, prompt_id: PromptId) -> PromptSpec:
        filename, version = _PROMPT_FILES[prompt_id]
        content = (self._root / filename).read_text(encoding="utf-8").strip()
        if not content:
            raise ValueError("prompt_content_empty")
        return PromptSpec(
            prompt_id=prompt_id,
            version=version,
            content_hash=sha256(content.encode("utf-8")).hexdigest(),
            content=content,
        )
