"""CLAUDE.md rules enforced as tests, so violations fail `make check`."""

import ast
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
SKIP_DIRS = {".venv", "tests", "__pycache__", "alembic"}

LLM_SDKS = {"anthropic", "openai", "google.generativeai", "google.genai", "mistralai", "cohere"}
PAYMENT_SDKS = {"stripe", "paystack", "paystackapi", "rave_python", "flutterwave"}


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
            # `from google import genai` imports the module google.genai.
            names.update(f"{node.module}.{a.name}" for a in node.names)
    return names


def _source_files() -> list[Path]:
    return [
        p for p in BACKEND.rglob("*.py") if not SKIP_DIRS.intersection(p.relative_to(BACKEND).parts)
    ]


def _violations(banned: set[str], allowed_prefix: Path) -> list[str]:
    bad = []
    for path in _source_files():
        if path.is_relative_to(allowed_prefix):
            continue
        for name in _imports(path):
            if name in banned or any(name.startswith(b + ".") for b in banned):
                bad.append(f"{path.relative_to(BACKEND)} imports {name}")
    return bad


def test_llm_sdks_only_imported_in_llm_package() -> None:
    assert _violations(LLM_SDKS, BACKEND / "llm") == []


def test_payment_sdks_only_imported_in_payment_adapters() -> None:
    assert _violations(PAYMENT_SDKS, BACKEND / "api" / "kehora_api" / "payments" / "adapters") == []


def test_import_check_sees_from_imports(tmp_path: Path) -> None:
    probe = tmp_path / "probe.py"
    probe.write_text("from google import genai\n", encoding="utf-8")
    assert "google.genai" in _imports(probe)


def test_backend_never_references_frontend() -> None:
    for path in _source_files():
        assert "Frontend/" not in path.read_text(encoding="utf-8"), path
