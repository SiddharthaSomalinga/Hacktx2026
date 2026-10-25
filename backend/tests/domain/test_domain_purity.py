"""The domain layer must stay pure: no I/O, no config, no clock, no outer layers (ARCH §3)."""

from __future__ import annotations

import ast
from pathlib import Path

DOMAIN = Path(__file__).resolve().parents[2] / "app" / "domain"

ALLOWED_STDLIB = {
    "__future__",
    "dataclasses",
    "datetime",
    "enum",
    "hashlib",
    "math",
    "re",
    "typing",
    "collections",
    "collections.abc",
    "itertools",
    "functools",
    "operator",
}
FORBIDDEN_CALLS = {("datetime", "now"), ("datetime", "utcnow"), ("date", "today"), ("time", "time")}


def _imports(tree: ast.AST) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


def test_domain_imports_only_pure_modules() -> None:
    offenders: dict[str, list[str]] = {}
    for path in DOMAIN.glob("*.py"):
        bad = [
            name
            for name in _imports(ast.parse(path.read_text()))
            if name not in ALLOWED_STDLIB and not name.startswith("app.domain")
        ]
        if bad:
            offenders[path.name] = sorted(bad)
    assert offenders == {}, f"domain reached outside itself: {offenders}"


def test_domain_never_reads_the_clock() -> None:
    offenders: list[str] = []
    for path in DOMAIN.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and (node.func.value.id, node.func.attr) in FORBIDDEN_CALLS
            ):
                offenders.append(f"{path.name}:{node.lineno}")
    assert offenders == [], f"domain reads the clock at {offenders}; take `now` as a parameter"
