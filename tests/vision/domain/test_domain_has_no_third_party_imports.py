"""The domain package must import nothing outside the standard library.

Enforced mechanically rather than by review. The constraint is easy to break
by accident - one `import numpy as np` for a convenience during a later phase -
and the cost is losing both hardware-free testability and portability to
constrained edge devices.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import caps_dash.vision.domain as domain_package

DOMAIN_DIR = Path(domain_package.__file__).parent
INTERNAL_PREFIX = "caps_dash.vision.domain"


def _import_roots(module_path: Path) -> set[str]:
    """Top-level package name of every import in one module."""
    tree = ast.parse(module_path.read_text(encoding="utf-8"), filename=str(module_path))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # relative import: stays inside the domain by definition
                continue
            if node.module:
                roots.add(node.module.split(".")[0])
    return roots


def test_domain_modules_import_only_stdlib() -> None:
    modules = sorted(DOMAIN_DIR.glob("*.py"))
    assert modules, "no domain modules found - has the package moved?"

    offenders: dict[str, set[str]] = {}
    for module_path in modules:
        third_party = {
            root
            for root in _import_roots(module_path)
            if root not in sys.stdlib_module_names and not root.startswith(INTERNAL_PREFIX)
        }
        # `caps_dash` itself would also be a violation: the domain is a leaf.
        if third_party:
            offenders[module_path.name] = third_party

    assert not offenders, (
        f"domain must stay dependency-free, found third-party imports: {offenders}"
    )


def test_domain_files_stay_small() -> None:
    """Project rule: source files under 200 lines; domain targets 150."""
    too_long = {
        path.name: len(path.read_text(encoding="utf-8").splitlines())
        for path in DOMAIN_DIR.glob("*.py")
        if len(path.read_text(encoding="utf-8").splitlines()) > 150
    }
    assert not too_long, f"domain modules over 150 lines: {too_long}"
