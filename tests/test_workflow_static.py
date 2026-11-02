"""Text-level guards on the GitHub Actions workflows (AUTO-02, Pitfalls 3 and 5).

No YAML library: the checks read lines and step blocks so they stay dependency-free.
"""

import re
from pathlib import Path

WORKFLOWS = Path(__file__).parent.parent / ".github" / "workflows"
NEWSLETTER = WORKFLOWS / "newsletter.yml"
CI = WORKFLOWS / "ci.yml"

DELIVERY_SECRETS = ("SMTP_USER", "SMTP_PASSWORD", "TEST_RECIPIENT", "SUBSCRIBERS_CSV")
STEP_PREFIX = "      - "
SHA_PIN = re.compile(r"uses:\s*[\w.-]+/[\w.-]+@[0-9a-f]{40}\b")


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _split(text: str) -> tuple[str, list[str]]:
    """Return (header before the first step, step blocks) for newsletter.yml."""
    lines = text.splitlines()
    starts = [i for i, line in enumerate(lines) if line.startswith(STEP_PREFIX)]
    assert starts, "no steps found"
    header = "\n".join(lines[: starts[0]])
    blocks = []
    for n, start in enumerate(starts):
        end = starts[n + 1] if n + 1 < len(starts) else len(lines)
        blocks.append("\n".join(lines[start:end]))
    return header, blocks


def _named(blocks: list[str], prefix: str) -> str:
    found = [b for b in blocks if b.startswith(f"{STEP_PREFIX}name: {prefix}")]
    assert len(found) == 1, f"expected one step named {prefix!r}"
    return found[0]


def _run_lines(text: str) -> list[str]:
    """Every line belonging to a `run:` value (inline or block scalar)."""
    out: list[str] = []
    lines = text.splitlines()
    for i, line in enumerate(lines):
        m = re.match(r"^(\s*)(?:- )?run:(.*)$", line)
        if not m:
            continue
        out.append(m.group(2))
        if m.group(2).strip() in ("|", ">", "|-", ">-"):
            indent = len(m.group(1))
            for nxt in lines[i + 1 :]:
                if nxt.strip() and len(nxt) - len(nxt.lstrip()) <= indent:
                    break
                out.append(nxt)
    return out


def test_delivery_secrets_only_in_deliver_and_failure_notice():
    header, blocks = _split(_text(NEWSLETTER))
    for name in DELIVERY_SECRETS:
        assert name not in header, f"{name} leaks into job/workflow level"
    allowed = {_named(blocks, "Deliver"), _named(blocks, "Failure notice")}
    for block in blocks:
        if block in allowed:
            continue
        for name in DELIVERY_SECRETS:
            assert name not in block, f"{name} appears outside delivery steps"


def test_build_step_gets_only_anthropic_key():
    _, blocks = _split(_text(NEWSLETTER))
    build = _named(blocks, "Build")
    assert "ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}" in build
    assert build.count("secrets.") == 1
    assert "python -m newsletter build --week \"$WEEK_INPUT\"" in build


def test_delivery_secret_values_are_mode_gated():
    _, blocks = _split(_text(NEWSLETTER))
    deliver = _named(blocks, "Deliver")
    assert "inputs.mode == 'test' && secrets.TEST_RECIPIENT || ''" in deliver
    assert "inputs.mode == 'send' && secrets.SUBSCRIBERS_CSV || ''" in deliver
    assert "inputs.mode == 'test' || inputs.mode == 'send'" in deliver
    notice = _named(blocks, "Failure notice")
    assert "failure() && inputs.mode != 'preview'" in notice
    assert "SUBSCRIBERS_CSV" not in notice
    assert 'notify-failure --mode "$MODE"' in notice


def test_anthropic_key_only_in_build():
    _, blocks = _split(_text(NEWSLETTER))
    holders = [b for b in blocks if "ANTHROPIC_API_KEY" in b]
    assert holders == [_named(blocks, "Build")]


def test_no_expression_interpolation_in_run_lines():
    for path in (NEWSLETTER, CI):
        for line in _run_lines(_text(path)):
            assert "${{" not in line, f"{path.name}: expression in run line: {line!r}"


def test_week_input_reaches_shell_via_env_only():
    text = _text(NEWSLETTER)
    assert "WEEK_INPUT: ${{ inputs.week }}" in text
    assert text.count("inputs.week") == 1


def test_permissions_read_only():
    for path in (NEWSLETTER, CI):
        text = _text(path)
        assert "contents: read" in text
        assert "contents: write" not in text
        assert "write-all" not in text


def test_dispatch_inputs():
    text = _text(NEWSLETTER)
    assert text.count("workflow_dispatch") == 1
    assert "default: preview" in text
    assert "options: [preview, test, send]" in text
    assert "group: newsletter" in text
    assert "cancel-in-progress: false" in text


def test_artifact_uploads_archive_only():
    _, blocks = _split(_text(NEWSLETTER))
    upload = _named(blocks, "Upload")
    assert "path: archive/" in upload
    assert "if: ${{ !cancelled() }}" in upload
    assert "retention-days: 14" in upload


def test_actions_pinned_to_commit_sha():
    for path in (NEWSLETTER, CI):
        uses = [line for line in _text(path).splitlines() if "uses:" in line]
        assert uses
        for line in uses:
            assert SHA_PIN.search(line), f"{path.name}: action not SHA-pinned: {line.strip()}"


def test_ci_runs_lint_and_tests_without_secrets():
    text = _text(CI)
    assert text.count("uv sync --frozen") == 1
    assert "secrets." not in text
    assert "uv run ruff check" in text
    assert "uv run pytest" in text
    assert "push" in text and "pull_request" in text
