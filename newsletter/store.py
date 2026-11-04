"""Archive paths and JSON/text IO for stage outputs."""

import json
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel

REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = REPO_ROOT / "templates"
PROMPTS_DIR = REPO_ROOT / "prompts"
# D-04: bump when a checkpoint payload changes shape; a mismatch means recompute.
CHECKPOINT_VERSION = 1


def archive_root() -> Path:
    return Path(os.environ.get("NEWSLETTER_ARCHIVE_DIR", "archive"))


def out_root() -> Path:
    return Path(os.environ.get("NEWSLETTER_OUT_DIR", "out"))


def week_dir(issue_id: str) -> Path:
    return archive_root() / issue_id


def _to_jsonable(obj: Any) -> Any:
    if isinstance(obj, BaseModel):
        return obj.model_dump(mode="json")
    if isinstance(obj, list):
        return [_to_jsonable(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _to_jsonable(v) for k, v in obj.items()}
    return obj


def _json_text(obj: Any) -> str:
    return json.dumps(_to_jsonable(obj), ensure_ascii=False, indent=2) + "\n"


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_json_text(obj), encoding="utf-8")


def write_json_atomic(path: Path, obj: Any) -> None:
    """Same JSON as write_json, written to a sibling .tmp file and moved into place with
    os.replace, so a crash never leaves a half-written checkpoint."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(_json_text(obj), encoding="utf-8")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def checkpoint_path(issue_id: str, stage: str) -> Path:
    return week_dir(issue_id) / "checkpoints" / f"{stage}.json"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_text(path: Path, s: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(s, encoding="utf-8")


def write_current(issue_id: str) -> None:
    write_json(archive_root() / "current.json", {"issue_id": issue_id})


def read_current() -> str:
    return read_json(archive_root() / "current.json")["issue_id"]
