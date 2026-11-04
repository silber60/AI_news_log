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


JOB_LINE = re.compile(r"^  [\w-]+:$")


def _blocks(lines: list[str]) -> tuple[str, list[str]]:
    starts = [i for i, line in enumerate(lines) if line.startswith(STEP_PREFIX)]
    assert starts, "no steps found"
    header = "\n".join(lines[: starts[0]])
    blocks = []
    for n, start in enumerate(starts):
        end = starts[n + 1] if n + 1 < len(starts) else len(lines)
        blocks.append("\n".join(lines[start:end]))
    return header, blocks


def _jobs(text: str) -> dict[str, tuple[str, list[str]]]:
    """Per job: (job header before its first step, its step blocks)."""
    lines = text.splitlines()
    top = lines.index("jobs:")
    starts = [i for i in range(top + 1, len(lines)) if JOB_LINE.match(lines[i])]
    assert starts, "no jobs found"
    jobs = {}
    for n, start in enumerate(starts):
        end = starts[n + 1] if n + 1 < len(starts) else len(lines)
        jobs[lines[start].strip().rstrip(":")] = _blocks(lines[start:end])
    return jobs


def _workflow_header(text: str) -> str:
    lines = text.splitlines()
    return "\n".join(lines[: lines.index("jobs:")])


def _split(text: str) -> tuple[str, list[str]]:
    """Return (workflow header + run job header, run job step blocks) for newsletter.yml."""
    header, blocks = _jobs(text)["run"]
    return _workflow_header(text) + "\n" + header, blocks


def _code(text: str) -> list[str]:
    """Non-comment lines."""
    return [line for line in text.splitlines() if not line.lstrip().startswith("#")]


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
    assert 'python -m newsletter build --week "$WEEK_INPUT"' in build


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
    ci = _text(CI)
    assert "contents: read" in ci
    assert "contents: write" not in ci
    assert "write-all" not in ci
    text = _text(NEWSLETTER)
    assert "write-all" not in text
    header = _code(_workflow_header(text))
    assert "  contents: read" in header
    assert not any("write" in line for line in header)
    run_header, _ = _jobs(text)["run"]
    assert "permissions:" not in run_header, "run job must keep the read-only workflow token"


def test_only_record_topic_job_has_write_scope():
    text = _text(NEWSLETTER)
    writes = [line for line in _code(text) if "contents: write" in line]
    assert len(writes) == 1
    jobs = _jobs(text)
    assert set(jobs) == {"run", "record-topic"}
    header, _ = jobs["record-topic"]
    assert "contents: write" in header
    for name, (job_header, blocks) in jobs.items():
        if name != "record-topic":
            assert "contents: write" not in job_header + "\n".join(blocks)


def test_record_topic_job_is_send_on_main_only_and_secret_free():
    header, blocks = _jobs(_text(NEWSLETTER))["record-topic"]
    job = header + "\n" + "\n".join(blocks)
    assert "needs: run" in header
    cond = [line for line in header.splitlines() if line.strip().startswith("if:")]
    assert len(cond) == 1
    assert "inputs.mode == 'send'" in cond[0]
    assert "github.ref == 'refs/heads/main'" in cond[0]
    assert "needs.run.result == 'success'" in cond[0]
    assert "secrets." not in job
    for name in DELIVERY_SECRETS + ("ANTHROPIC_API_KEY",):
        assert name not in job, f"{name} reaches the record-topic job"
    checkout = [b for b in blocks if "actions/checkout@" in b]
    assert len(checkout) == 1
    assert "persist-credentials: false" in checkout[0]
    assert 'record-topic --mode "$MODE"' in _named(blocks, "Append explainer topic")


def test_job_token_only_in_build_and_topic_commit():
    jobs = _jobs(_text(NEWSLETTER))
    _, run_blocks = jobs["run"]
    _, record_blocks = jobs["record-topic"]
    allowed = [_named(run_blocks, "Build"), _named(record_blocks, "Commit topic record")]
    holders = [b for _, blocks in jobs.values() for b in blocks if "github.token" in b]
    assert holders == allowed
    for header, _ in jobs.values():
        assert "github.token" not in header
    assert "github.token" not in _workflow_header(_text(NEWSLETTER))


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


def test_build_step_gets_job_token_not_a_secret():
    # D-09: the GitHub license API call uses the read-only job token.
    _, blocks = _split(_text(NEWSLETTER))
    build = _named(blocks, "Build")
    assert "GITHUB_TOKEN: ${{ github.token }}" in build
    assert build.count("secrets.") == 1
    assert "secrets.GITHUB_TOKEN" not in _text(NEWSLETTER)
    holders = [b for b in blocks if "GITHUB_TOKEN" in b]
    assert holders == [build]
