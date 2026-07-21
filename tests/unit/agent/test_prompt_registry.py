from hashlib import sha256

import pytest

from opercerta.agent.prompt_registry import PromptId, PromptRegistry


def test_prompt_registry_loads_versioned_prompt_and_hash(tmp_path) -> None:
    content = "只生成受控的只读调查计划。\n"
    (tmp_path / "planner-v1.md").write_text(content, encoding="utf-8")

    prompt = PromptRegistry(tmp_path).load(PromptId.PLANNER)

    assert prompt.prompt_id is PromptId.PLANNER
    assert prompt.version == "v1"
    assert prompt.content == content.strip()
    assert prompt.content_hash == sha256(content.strip().encode("utf-8")).hexdigest()


def test_prompt_registry_fails_closed_on_empty_prompt(tmp_path) -> None:
    (tmp_path / "analyst-v1.md").write_text("   \n", encoding="utf-8")

    with pytest.raises(ValueError, match="prompt_content_empty"):
        PromptRegistry(tmp_path).load(PromptId.ANALYST)


def test_prompt_registry_fails_closed_on_missing_prompt(tmp_path) -> None:
    with pytest.raises(FileNotFoundError):
        PromptRegistry(tmp_path).load(PromptId.VERIFIER)


def test_all_packaged_prompts_are_versioned_and_non_empty() -> None:
    registry = PromptRegistry.packaged()

    prompts = [registry.load(prompt_id) for prompt_id in PromptId]

    assert {prompt.prompt_id for prompt in prompts} == set(PromptId)
    assert {prompt.version for prompt in prompts} == {"v1"}
    assert all(len(prompt.content_hash) == 64 for prompt in prompts)
