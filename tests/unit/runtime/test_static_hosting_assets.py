from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_netlify_build_is_static_and_supports_console_route() -> None:
    content = (ROOT / "netlify.toml").read_text(encoding="utf-8")

    assert 'base = "web"' in content
    assert 'command = "npm run build"' in content
    assert 'publish = "dist"' in content
    assert 'from = "/*"' in content
    assert 'to = "/index.html"' in content
