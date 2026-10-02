from __future__ import annotations

import re
from pathlib import Path
from typing import Any


OBSERVER_FILENAME = "prospective-holdout-observer.yml"
_NAME_RE = re.compile(r"^name:\s*(.+?)\s*$", re.MULTILINE)
_WORKFLOWS_RE = re.compile(r"^\s*workflows:\s*\[(.*?)\]\s*$", re.MULTILINE)
_QUOTED_VALUE_RE = re.compile(r"[\"']([^\"']+)[\"']")


def _workflow_name(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    match = _NAME_RE.search(text)
    if not match:
        raise ValueError(f"workflow has no top-level name: {path}")
    value = match.group(1).strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
    if not value:
        raise ValueError(f"workflow has empty top-level name: {path}")
    return value


def _watched_workflows(observer_path: Path) -> list[str]:
    text = observer_path.read_text(encoding="utf-8")
    match = _WORKFLOWS_RE.search(text)
    if not match:
        raise ValueError(f"observer has no workflow_run workflows list: {observer_path}")
    watched = _QUOTED_VALUE_RE.findall(match.group(1))
    if not watched:
        raise ValueError(f"observer workflow list is empty or unquoted: {observer_path}")
    return sorted(set(watched))


def audit_observer_coverage(workflows_dir: Path | str) -> dict[str, Any]:
    workflows_dir = Path(workflows_dir)
    observer_path = workflows_dir / OBSERVER_FILENAME
    if not observer_path.is_file():
        raise FileNotFoundError(observer_path)

    workflow_paths = sorted(
        {
            *workflows_dir.glob("*.yml"),
            *workflows_dir.glob("*.yaml"),
        }
    )
    production_workflows = sorted(
        _workflow_name(path)
        for path in workflow_paths
        if path.name != OBSERVER_FILENAME
    )
    watched_workflows = _watched_workflows(observer_path)

    production_set = set(production_workflows)
    watched_set = set(watched_workflows)
    missing = sorted(production_set - watched_set)
    extra = sorted(watched_set - production_set)

    return {
        "complete": not missing and not extra,
        "production_workflows": production_workflows,
        "watched_workflows": watched_workflows,
        "missing": missing,
        "extra": extra,
    }
