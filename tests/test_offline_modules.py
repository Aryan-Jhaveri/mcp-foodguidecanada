"""Static offline proof: the runtime offline modules never import network code.

Real file reads, no mocks: each module's source is parsed with ``ast`` and any
``Import`` / ``ImportFrom`` whose module name is or starts with ``requests``,
``urllib.request`` or ``urllib.error`` fails the check with the offending line
number. ``urllib.parse`` is fine (cnf/db.py uses it only to build a read-only
``sqlite3`` URI).

Excluded on purpose (build-time modules that legitimately fetch pages and so
import ``requests``/``urllib`` — they must not dial out at run time from the
offline paths, which the subprocess tests in test_offline_subprocess.py prove
with dead proxies): ``foodguide/cli.py``, ``foodguide/builders/*``,
``foodguide/pipeline/*``, ``foodguide/api/cnf*.py``, ``foodguide/api/dri.py``,
``foodguide/api/eer.py``, ``foodguide/recipes/fetch.py`` and
``foodguide/recipes/builder.py``.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

BANNED_ROOTS = ("requests", "urllib.request", "urllib.error")

#: src-relative paths of every module the offline runtime paths lean on.
OFFLINE_MODULES = [
    "foodguide/data_manager.py",
    "foodguide/config.py",
    "foodguide/cnf/db.py",
    "foodguide/cnf/mcp_source.py",
    "foodguide/recipes/source.py",
    "foodguide/api/recipe.py",
    "foodguide/db/connection.py",
    "foodguide/db/queries.py",
    "foodguide/db/schema.py",
    "foodguide/db/sql_engine.py",
    "foodguide/db/cnf_tools.py",
    "foodguide/db/dri_tools.py",
    "foodguide/db/eer_tools.py",
    "foodguide/db/math_tools.py",
]

SRC = Path(__file__).resolve().parents[1] / "src"


def _banned_imports(module_path: Path) -> list[str]:
    """All banned Import/ImportFrom nodes in *module_path* as 'line: name'."""
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    banned = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            # Relative imports have module=None; only absolute names matter here.
            names = [node.module] if node.module else []
        else:
            continue
        for name in names:
            if any(name == root or name.startswith(root + ".") for root in BANNED_ROOTS):
                banned.append(f"line {node.lineno}: imports {name}")
    return banned


@pytest.mark.parametrize("module_rel", OFFLINE_MODULES)
def test_offline_module_never_imports_network_code(module_rel: str) -> None:
    module_path = SRC / module_rel
    assert module_path.is_file(), f"expected source file missing: {module_path}"
    banned = _banned_imports(module_path)
    assert not banned, (
        f"{module_rel} is an offline module but imports network code: "
        + "; ".join(banned)
    )
