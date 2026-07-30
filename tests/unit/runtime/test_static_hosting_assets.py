from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_netlify_build_is_static_and_supports_console_route() -> None:
    content = (ROOT / "netlify.toml").read_text(encoding="utf-8")

    assert 'base = "web"' in content
    assert 'command = "npm run build"' in content
    assert 'publish = "dist"' in content
    assert 'from = "/*"' in content
    assert 'to = "/index.html"' in content


def test_netlify_static_showcase_sets_browser_security_headers() -> None:
    content = (ROOT / "netlify.toml").read_text(encoding="utf-8")

    for header in (
        "Content-Security-Policy",
        "Cross-Origin-Opener-Policy",
        "Permissions-Policy",
        "Referrer-Policy",
        "X-Content-Type-Options",
        "X-Frame-Options",
    ):
        assert header in content


def test_vite_local_proxy_targets_the_compose_api_port() -> None:
    content = (ROOT / "web" / "vite.config.ts").read_text(encoding="utf-8")

    assert '"/api": "http://127.0.0.1:8080"' in content


def test_netlify_local_link_state_is_ignored() -> None:
    content = (ROOT / ".gitignore").read_text(encoding="utf-8")

    assert ".netlify/" in content


def test_showcase_visual_contract_avoids_scroll_traps_and_heavy_generated_treatments() -> None:
    css = (ROOT / "web" / "src" / "styles.css").read_text(encoding="utf-8")

    for forbidden in (
        "position: fixed",
        "position: sticky",
        "scroll-snap-type",
        "animation-iteration-count: infinite",
    ):
        assert forbidden not in css
    assert "prefers-reduced-motion" in css
    assert "--scenario-inventory" in css
    assert "--scenario-equipment" in css
    assert "--scenario-task" in css
    assert "--showcase-title-mobile: clamp(2rem, 9vw, 2.2rem)" in css
