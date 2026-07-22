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


def test_planner_prompt_freezes_machine_readable_enum_values() -> None:
    content = PromptRegistry.packaged().load(PromptId.PLANNER).content

    for literal in (
        "subject",
        "policy",
        "knowledge",
        "query_reported",
        "approved_work_order_verified",
        "snake_case",
    ):
        assert literal in content


def test_structured_prompts_declare_exact_output_fields_and_decisions() -> None:
    registry = PromptRegistry.packaged()
    analyst = registry.load(PromptId.ANALYST).content
    verifier = registry.load(PromptId.VERIFIER).content
    reporter = registry.load(PromptId.REPORTER).content

    for field in ("summary", "recommendation", "uncertainties", "citations"):
        assert field in analyst
    for literal in ("proceed", "abort", "escalate", "proposed_plan"):
        assert literal in verifier
    for field in ("outcome", "summary", "evidence_refs", "citations", "snake_case"):
        assert field in reporter
