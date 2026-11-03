"""Committed record of past explainer topics (EXPL-02, D-06, D-15).

The file holds issue_id, date and topic only. The build reads it through
load_past(); only `python -m newsletter record-topic --mode send` appends to it.
"""

import json
import logging
import os
from datetime import timedelta
from pathlib import Path

from newsletter import store
from newsletter.schema import Issue

log = logging.getLogger(__name__)

VERSION = 1
MAX_PAST = 52


def topics_path() -> Path:
    env = os.environ.get("NEWSLETTER_TOPICS_PATH")
    return Path(env) if env else store.REPO_ROOT / "data" / "explainer_topics.json"


def _valid_entry(e: object) -> bool:
    return (
        isinstance(e, dict)
        and isinstance(e.get("issue_id"), str)
        and isinstance(e.get("date"), str)
        and isinstance(e.get("topic"), str)
    )


def _read(path: Path) -> list[dict] | None:
    """Return the entries, or None when the file is missing or not the version-1 shape."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError, ValueError:
        return None
    if not isinstance(data, dict) or data.get("version") != VERSION:
        return None
    topics = data.get("topics")
    if not isinstance(topics, list) or not all(_valid_entry(e) for e in topics):
        return None
    return topics


def load_past(path: Path | None = None) -> list[str]:
    """Past topic strings, newest issue first, at most MAX_PAST."""
    entries = _read(path or topics_path())
    if entries is None:
        log.warning("topics=unreadable")
        return []
    entries = sorted(entries, key=lambda e: e["issue_id"], reverse=True)
    return [e["topic"] for e in entries[:MAX_PAST]]


def record(issue: Issue, path: Path | None = None) -> bool:
    """Append this issue's explainer topic once per issue_id. True when the file changed."""
    if issue.explainer is None:
        return False
    p = path or topics_path()
    if p.exists():
        entries = _read(p)
        if entries is None:
            raise ValueError("topic record is not a valid version-1 file")
    else:
        entries = []
    if any(e["issue_id"] == issue.issue_id for e in entries):
        return False
    entries.append(
        {
            "issue_id": issue.issue_id,
            # send Monday in KST, same rule as render.date_line; never runner time
            "date": (issue.week_end + timedelta(days=1)).isoformat(),
            "topic": issue.explainer.topic,
        }
    )
    entries.sort(key=lambda e: e["issue_id"])
    p.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps({"version": VERSION, "topics": entries}, ensure_ascii=False, indent=2)
    p.write_text(text + "\n", encoding="utf-8")
    return True


# similarity rule: plan 03-04 (normalize_key, ALIASES, is_repeat go here)
