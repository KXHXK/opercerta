from pathlib import Path

import pytest

from scripts.ingest_knowledge import check_knowledge_assets

ROOT = Path(__file__).resolve().parents[3]


def test_three_synthetic_sop_assets_have_fixed_versions_and_chunks() -> None:
    report = check_knowledge_assets(ROOT)

    assert report.embedding_model == "BAAI/bge-small-zh-v1.5"
    assert report.embedding_dimension == 512
    assert report.document_count == 3
    assert report.scenarios == ("equipment", "inventory", "task")
    assert report.chunk_count >= 9


def test_asset_check_rejects_a_changed_file_without_manifest_update(tmp_path: Path) -> None:
    knowledge_dir = tmp_path / "data" / "knowledge"
    knowledge_dir.mkdir(parents=True)
    source = ROOT / "data" / "knowledge"
    for path in source.iterdir():
        if path.is_file():
            (knowledge_dir / path.name).write_bytes(path.read_bytes())
    inventory = knowledge_dir / "inventory-replenishment-v1.md"
    inventory.write_text(inventory.read_text(encoding="utf-8") + "\n未登记变更。\n")

    with pytest.raises(ValueError, match="knowledge_source_checksum_mismatch"):
        check_knowledge_assets(tmp_path)
