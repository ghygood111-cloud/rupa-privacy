import ast
import re
from pathlib import Path

import rupa_privacy


ABSOLUTE_PATH = re.compile(r"^(?:[A-Za-z]:[\\/]|\\\\|/(?:home|Users|tmp|var|opt|etc)/)")


def test_distributed_source_contains_no_hard_coded_absolute_path():
    package_root = Path(next(iter(rupa_privacy.__path__)))
    findings = []
    for path in package_root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if ABSOLUTE_PATH.match(node.value):
                    findings.append((path.name, node.lineno, node.value))
    assert findings == []
