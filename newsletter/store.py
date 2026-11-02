"""Archive paths and JSON/text IO for stage outputs."""

import json
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel

REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = REPO_ROOT / "templates"
PROMPTS_DIR = REPO_ROOT / "prompts"


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


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(_to_jsonable(obj), ensure_ascii=False, indent=2)
    path.write_text(text + "\n", encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_text(path: Path, s: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(s, encoding="utf-8")


def write_current(issue_id: str) -> None:
    write_json(archive_root() / "current.json", {"issue_id": issue_id})


def read_current() -> str:
    return read_json(archive_root() / "current.json")["issue_id"]
