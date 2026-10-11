from pathlib import Path


def test_gitignore_excludes_private_runtime_data() -> None:
    root = Path(__file__).parents[2]
    ignore = (root / ".gitignore").read_text(encoding="utf-8")
    for pattern in (".env", "data/*", "*.db", "data/raw/*", "data/processed/*", "data/vector/*", "__pycache__/"):
        assert pattern in ignore


def test_docker_build_context_excludes_runtime_data_and_secrets() -> None:
    root = Path(__file__).parents[2]
    ignore = (root / ".dockerignore").read_text(encoding="utf-8")
    for pattern in (".env", "data/", "**/*.db", ".venv/", "**/__pycache__/"):
        assert pattern in ignore

    dockerfile = (root / "docker" / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY data" not in dockerfile


def test_default_host_bindings_are_loopback_only() -> None:
    root = Path(__file__).parents[2]
    env = (root / ".env.example").read_text(encoding="utf-8")
    settings = (root / "app" / "core" / "config.py").read_text(encoding="utf-8")
    powershell = (root / "scripts" / "run.ps1").read_text(encoding="utf-8")
    shell = (root / "scripts" / "run.sh").read_text(encoding="utf-8")
    compose = (root / "docker" / "docker-compose.yml").read_text(encoding="utf-8")

    assert "API_HOST=127.0.0.1" in env
    assert 'api_host: str = "127.0.0.1"' in settings
    assert 'else { "127.0.0.1" }' in powershell
    assert '${API_HOST:-127.0.0.1}' in shell
    assert '127.0.0.1:8000:8000' in compose
    assert '11434:11434' not in compose


def test_version_metadata_is_aligned() -> None:
    root = Path(__file__).parents[2]
    package = (root / "pyproject.toml").read_text(encoding="utf-8")
    config = (root / "app" / "core" / "config.py").read_text(encoding="utf-8")
    env = (root / ".env.example").read_text(encoding="utf-8")
    html = (root / "app" / "ui" / "static" / "index.html").read_text(encoding="utf-8")

    assert 'version = "1.5.4"' in package
    assert 'app_version: str = "1.5.4"' in config
    assert "APP_VERSION=1.5.4" in env
    assert "Tungelligence v1.5.4" in html
