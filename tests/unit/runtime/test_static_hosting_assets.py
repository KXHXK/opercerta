from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_netlify_build_is_static_and_supports_console_route() -> None:
    content = (ROOT / "netlify.toml").read_text(encoding="utf-8")

    assert 'base = "web"' in content
    assert 'command = "npm run build"' in content
    assert 'publish = "dist"' in content
    assert 'from = "/*"' in content
    assert 'to = "/index.html"' in content


def test_vite_local_proxy_targets_the_compose_api_port() -> None:
    content = (ROOT / "web" / "vite.config.ts").read_text(encoding="utf-8")

    assert '"/api": "http://127.0.0.1:8080"' in content


def test_netlify_local_link_state_is_ignored() -> None:
    content = (ROOT / ".gitignore").read_text(encoding="utf-8")

    assert ".netlify/" in content
