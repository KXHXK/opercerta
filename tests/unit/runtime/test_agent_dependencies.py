import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_langchain_core_is_direct_and_top_level_agent_package_is_absent() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    dependencies = project["dependencies"]

    assert "langchain-core==1.4.9" in dependencies
    assert not any(dependency.startswith("langchain==") for dependency in dependencies)
