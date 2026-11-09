"""Text-level guards on the GitHub Actions workflows (AUTO-02, Pitfalls 3 and 5).

No YAML library: the checks read lines and step blocks so they stay dependency-free.
"""

import json
import re
from pathlib import Path

WORKFLOWS = Path(__file__).parent.parent / ".github" / "workflows"
NEWSLETTER = WORKFLOWS / "newsletter.yml"
CI = WORKFLOWS / "ci.yml"
PAGES = WORKFLOWS / "pages.yml"
IMPORT = WORKFLOWS / "import-subscribers.yml"
DEPLOY_PAGES_PIN = "actions/deploy-pages@368f82528645a54fb793d4d04e342629a3f51346"
UPLOAD_PAGES_PIN = "actions/upload-pages-artifact@fc324d3547104276b827a68afc52ff2a11cc49c9"

UNSUBSCRIBE_SECRETS = ("UNSUBSCRIBE_TOKEN_SECRET", "UNSUBSCRIBE_LIST_KEY")
DELIVERY_SECRETS = (
    "SMTP_USER",
    "SMTP_PASSWORD",
    "TEST_RECIPIENT",
    "SUBSCRIBERS_CSV",
    "SUBSCRIBER_LIST_KEY",
    *UNSUBSCRIBE_SECRETS,
)
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


def test_delivery_secrets_only_in_deliver_and_report():
    header, blocks = _split(_text(NEWSLETTER))
    for name in DELIVERY_SECRETS:
        assert name not in header, f"{name} leaks into job/workflow level"
    allowed = {_named(blocks, "Deliver"), _named(blocks, "Report")}
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
    assert 'python -m newsletter build --week "$WEEK_INPUT" --force-stage "$FORCE_STAGE"' in build
    assert "${{" not in build.split("run:", 1)[1]  # no expression in the run line (T-05-09)


def test_delivery_secret_values_are_mode_gated():
    _, blocks = _split(_text(NEWSLETTER))
    deliver = _named(blocks, "Deliver")
    # Phase 5: the gates read env.MODE, which also covers scheduled runs (Pitfall 6).
    assert "env.MODE == 'test' && secrets.TEST_RECIPIENT || ''" in deliver
    assert "env.MODE == 'send' && secrets.SUBSCRIBERS_CSV || ''" in deliver
    assert "if: ${{ env.MODE == 'test' || env.MODE == 'send' }}" in deliver
    assert "inputs.mode" not in deliver
    report = _named(blocks, "Report")
    assert "if: ${{ always() && env.MODE != 'preview' }}" in report
    assert "SUBSCRIBERS_CSV" not in report
    assert "SUBSCRIBER_LIST_KEY" not in report
    assert 'uv run python -m newsletter report --mode "$MODE"' in report
    # owner-notice credentials and TEST_RECIPIENT only (T-05-17)
    assert sorted(re.findall(r"secrets\.(\w+)", report)) == [
        "SMTP_PASSWORD",
        "SMTP_USER",
        "TEST_RECIPIENT",
    ]


def test_no_failure_notice_step_remains():
    text = _text(NEWSLETTER)
    _, blocks = _split(text)
    assert not any(b.startswith(f"{STEP_PREFIX}name: Failure notice") for b in blocks)
    assert "notify-failure" not in "\n".join(_code(text))


def test_unsubscribe_secrets_only_in_deliver():
    # 04-05 (D-13, T-04-15): the token secret serves test and send; the list key is
    # send-only. Neither reaches the Report, Build, publish or deploy jobs.
    text = _text(NEWSLETTER)
    _, blocks = _split(text)
    deliver = _named(blocks, "Deliver")
    assert "UNSUBSCRIBE_TOKEN_SECRET: ${{ secrets.UNSUBSCRIBE_TOKEN_SECRET }}" in deliver
    assert (
        "UNSUBSCRIBE_LIST_KEY: ${{ env.MODE == 'send' && secrets.UNSUBSCRIBE_LIST_KEY || '' }}"
        in deliver
    )
    report = _named(blocks, "Report")
    for name in UNSUBSCRIBE_SECRETS:
        assert name not in report
        assert text.count(name) == deliver.count(name), f"{name} appears outside Deliver"
    assert text.count("UNSUBSCRIBE_") == 2 + 2  # two env lines, name and secrets.<name> each


def test_anthropic_key_only_in_build():
    _, blocks = _split(_text(NEWSLETTER))
    holders = [b for b in blocks if "ANTHROPIC_API_KEY" in b]
    assert holders == [_named(blocks, "Build")]


def test_no_expression_interpolation_in_run_lines():
    for path in (NEWSLETTER, CI, PAGES, IMPORT):
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


def test_only_publish_job_has_write_scope():
    text = _text(NEWSLETTER)
    writes = [line for line in _code(text) if "contents: write" in line]
    assert len(writes) == 1
    jobs = _jobs(text)
    assert set(jobs) == {"run", "publish", "deploy-pages"}
    header, _ = jobs["publish"]
    assert "contents: write" in header
    for name, (job_header, blocks) in jobs.items():
        if name != "publish":
            assert "contents: write" not in job_header + "\n".join(blocks)


def test_pages_scopes_only_on_deploy_jobs():
    for path, deploy in ((NEWSLETTER, "deploy-pages"), (PAGES, "deploy")):
        jobs = _jobs(_text(path))
        for name, (header, blocks) in jobs.items():
            job = "\n".join(_code(header + "\n" + "\n".join(blocks)))
            if name == deploy:
                assert "pages: write" in job and "id-token: write" in job, path.name
            else:
                assert "pages: write" not in job, (path.name, name)
                assert "id-token: write" not in job, (path.name, name)
        assert not any("write" in line for line in _code(_workflow_header(_text(path))))


def test_deploy_jobs_are_secret_free_and_checkout_free():
    for path, deploy in ((NEWSLETTER, "deploy-pages"), (PAGES, "deploy")):
        header, blocks = _jobs(_text(path))[deploy]
        job = header + "\n" + "\n".join(blocks)
        assert "secrets." not in job, path.name
        assert "github.token" not in job, path.name
        assert "actions/checkout@" not in job, path.name
        assert "name: github-pages" in header
        assert "group: pages" in header and "cancel-in-progress: false" in header
        assert len(blocks) == 1 and DEPLOY_PAGES_PIN in blocks[0]
    header, _ = _jobs(_text(NEWSLETTER))["deploy-pages"]
    assert "needs: [run, publish]" in header
    cond = [line.strip() for line in header.splitlines() if line.strip().startswith("if:")]
    assert len(cond) == 1
    assert cond[0].startswith("if: ${{ !cancelled() && ")
    assert "needs.run.outputs.outcome == 'sent'" in cond[0]
    assert "needs.publish.result == 'success'" in cond[0]


def test_publish_job_commits_every_run_on_main_and_is_secret_free():
    # AUTO-03, D-04: always() so a failed or cancelled run still commits archive/ and the
    # ledger; preview commits nothing; the sent-only steps carry their own gate.
    header, blocks = _jobs(_text(NEWSLETTER))["publish"]
    job = header + "\n" + "\n".join(blocks)
    assert "needs: run" in header
    cond = [line for line in _code(header) if line.strip().startswith("if:")]
    assert len(cond) == 1
    assert cond[0].strip().startswith("if: ${{ always() && ")
    assert "github.ref == 'refs/heads/main'" in cond[0]
    assert "(github.event_name == 'schedule' || inputs.mode != 'preview')" in cond[0]
    assert "needs.run.result" not in cond[0]
    assert "secrets." not in job
    for name in DELIVERY_SECRETS + ("ANTHROPIC_API_KEY",):
        assert name not in job, f"{name} reaches the publish job"
    checkout = [b for b in blocks if "actions/checkout@" in b]
    assert len(checkout) == 1
    assert "persist-credentials: false" in checkout[0]
    downloads = [b for b in blocks if "actions/download-artifact@" in b]
    assert len(downloads) == 2
    assert "name: issue-${{ github.run_id }}" in downloads[0] and "path: archive/" in downloads[0]
    assert "name: ledger-${{ github.run_id }}" in downloads[1]
    assert "path: data/ledger/" in downloads[1]
    for block in downloads:
        assert "continue-on-error: true" in block
    assert "MODE: ${{ needs.run.outputs.mode }}" in header
    assert "OUTCOME: ${{ needs.run.outputs.outcome }}" in header
    sent_only = "if: ${{ env.OUTCOME == 'sent' }}"
    topic = _named(blocks, "Append explainer topic")
    web = _named(blocks, "Publish web pages")
    assert 'record-topic --mode "$MODE"' in topic and sent_only in topic
    assert 'newsletter publish --mode "$MODE"' in web and sent_only in web
    commit = _named(blocks, "Commit archive, ledger, record and pages")
    assert "if:" not in commit  # commits after every non-preview run
    paths = "for path in archive data/ledger data/explainer_topics.json data/issues docs; do"
    assert paths in commit
    assert 'if [ -e "$path" ]; then git add -- "$path"; fi' in commit
    assert "git diff --cached --quiet && exit 0" in commit
    assert 'git commit -m "chore(newsletter): archive, ledger and publish"' in commit
    assert "for i in 1 2 3; do" in commit and "sleep $((i * 5))" in commit
    assert "set -x" not in commit and "echo" not in commit
    assert "git config user.name silber60" in commit
    assert "git config user.email 81203897+silber60@users.noreply.github.com" in commit
    upload = blocks[-1]
    assert UPLOAD_PAGES_PIN in upload and "path: docs/" in upload
    assert sent_only in upload  # Pitfall 4: a paused or failed week publishes nothing


def test_pages_workflow_triggers_and_build():
    text = _text(PAGES)
    assert "workflow_dispatch:" in text
    assert "branches: [main]" in text
    assert 'paths: ["docs/**"]' in text
    assert "  contents: read" in _workflow_header(text)
    jobs = _jobs(text)
    assert set(jobs) == {"build", "deploy"}
    _, blocks = jobs["build"]
    assert "secrets." not in text
    assert "persist-credentials: false" in blocks[0]
    assert UPLOAD_PAGES_PIN in blocks[1] and "path: docs/" in blocks[1]


def test_job_token_only_in_build_and_publish_commit():
    jobs = _jobs(_text(NEWSLETTER))
    _, run_blocks = jobs["run"]
    _, publish_blocks = jobs["publish"]
    allowed = [
        _named(run_blocks, "Build"),
        _named(publish_blocks, "Commit archive, ledger, record and pages"),
    ]
    holders = [b for _, blocks in jobs.values() for b in blocks if "github.token" in b]
    assert holders == allowed
    for header, _ in jobs.values():
        assert "github.token" not in header
    assert "github.token" not in _workflow_header(_text(NEWSLETTER))
    assert "github.token" not in _text(PAGES)


def test_dispatch_inputs():
    text = _text(NEWSLETTER)
    assert text.count("workflow_dispatch") == 1
    assert "default: preview" in text
    assert "options: [preview, test, send]" in text
    assert "group: newsletter" in text
    assert "cancel-in-progress: false" in text
    # D-03: the stale override is a deliberate dispatch choice, off by default.
    block = text.split("      allow_stale:\n", 1)[1].split("\n\n", 1)[0]
    assert block.startswith("        description: ")
    assert "        type: boolean\n        default: false" in block
    assert text.count("inputs.allow_stale") == 1
    assert "ALLOW_STALE: ${{ inputs.allow_stale }}" in text


def test_force_stage_input_reaches_build_via_env_only():
    """05-02, D-04: a dispatch choice, default none; a schedule passes '' (reuse all)."""
    from newsletter.pipeline import STAGES

    text = _text(NEWSLETTER)
    block = text.split("      force_stage:\n", 1)[1].split("\n\n", 1)[0]
    assert block.startswith("        description: ")
    assert "        type: choice\n" in block
    assert f"        options: [{', '.join(('none', *STAGES))}]\n" in block
    assert "        default: none" in block
    assert text.count("inputs.force_stage") == 1
    run_header, _ = _jobs(text)["run"]
    assert "FORCE_STAGE: ${{ inputs.force_stage }}" in run_header
    assert text.count('--force-stage "$FORCE_STAGE"') == 1


def test_artifact_uploads_archive_only():
    _, blocks = _split(_text(NEWSLETTER))
    upload = _named(blocks, "Upload")
    assert "path: archive/" in upload
    assert "if: ${{ always() }}" in upload  # Pitfall 3: a timeout or cancel keeps the archive
    assert "overwrite: true" in upload
    assert "retention-days: 14" in upload
    ledger = _named(blocks, "Ledger artifact")
    assert "if: ${{ always() && env.MODE == 'send' }}" in ledger
    assert "name: ledger-${{ github.run_id }}" in ledger
    assert "path: data/ledger/" in ledger
    assert "if-no-files-found: ignore" in ledger
    assert "overwrite: true" in ledger and "retention-days: 14" in ledger
    assert "secrets." not in ledger


def test_actions_pinned_to_commit_sha():
    for path in (NEWSLETTER, CI, PAGES, IMPORT):
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


# ------------------------------------------- live list and one-time import (04.1-03)


def test_subscriber_list_key_send_gated_in_deliver_only():
    # D-08, T-04.1-10: the members key reaches only the send-mode Deliver step.
    text = _text(NEWSLETTER)
    _, blocks = _split(text)
    deliver = _named(blocks, "Deliver")
    line = "SUBSCRIBER_LIST_KEY: ${{ env.MODE == 'send' && secrets.SUBSCRIBER_LIST_KEY || '' }}"
    assert line in deliver
    assert text.count("SUBSCRIBER_LIST_KEY") == deliver.count("SUBSCRIBER_LIST_KEY") == 2
    for block in blocks:
        if block != deliver:
            assert "SUBSCRIBER_LIST_KEY" not in block
    for name, (header, job_blocks) in _jobs(text).items():
        if name != "run":
            assert "SUBSCRIBER_LIST_KEY" not in header + "\n".join(job_blocks)
    assert "SUBSCRIBE_ADMIN_KEY" not in text
    assert text.count("UNSUBSCRIBE_") == 4
    assert _named(blocks, "Build").count("secrets.") == 1


def test_import_workflow_is_dispatch_only_and_serialized():
    text = _text(IMPORT)
    header = _workflow_header(text)
    assert "\non:\n  workflow_dispatch:\n\npermissions:" in header  # the only trigger
    assert "inputs:" not in text
    for other in ("push", "pull_request", "schedule", "workflow_run", "repository_dispatch"):
        assert f"{other}:" not in text
    assert "group: newsletter" in header
    assert "cancel-in-progress: false" in header
    assert "queue: max" in header
    assert set(_jobs(text)) == {"import"}


def test_import_workflow_secrets_only_in_import_step():
    # D-06, T-04.1-12: both secrets in the one step, nowhere else, and no log helpers.
    text = _text(IMPORT)
    _, blocks = _jobs(text)["import"]
    step = _named(blocks, "Import subscribers")
    assert text.count("secrets.") == step.count("secrets.") == 2
    assert "SUBSCRIBERS_CSV: ${{ secrets.SUBSCRIBERS_CSV }}" in step
    assert "SUBSCRIBE_ADMIN_KEY: ${{ secrets.SUBSCRIBE_ADMIN_KEY }}" in step
    for name in ("SUBSCRIBERS_CSV", "SUBSCRIBE_ADMIN_KEY"):
        assert text.count(name) == step.count(name) == 2, name
    assert "uv run python -m newsletter import-subscribers" in step
    assert "upload-artifact" not in text
    assert "set -x" not in text
    assert "echo" not in text
    assert "github.token" not in text
    checkout = [b for b in blocks if "actions/checkout@" in b]
    assert len(checkout) == 1 and "persist-credentials: false" in checkout[0]


def test_import_workflow_permissions_read_only():
    text = _text(IMPORT)
    code = _code(text)
    assert sum(1 for ln in code if ln.strip() == "permissions:") == 1
    assert "permissions:" in _workflow_header(text)
    assert "  contents: read" in _workflow_header(text)
    for name, (header, blocks) in _jobs(text).items():
        assert "permissions:" not in header + "\n".join(blocks), name
    assert not any(": write" in ln for ln in text.splitlines())
    assert "write-all" not in text


# ------------------------------------------------- schedule, pause and outcome (05-01)

SEND_CRONS = ["17 8 * * 1", "17 10 * * 1", "47 12 * * 1"]
SEND_CRON = SEND_CRONS[0]
TEST_CRON = "47 5 * * 1"


def _cron_lines(text: str) -> list[str]:
    return [line.strip() for line in _code(text) if line.strip().startswith("- cron:")]


def test_kst_crons_off_the_hour_with_backup_sends():
    # 2026-11-09: GitHub ran 06:00 3.5 h late and dropped 08:00; crons now avoid :00 and
    # two backup sends retry (the ledger keeps them from mailing anyone twice).
    code = _code(_text(NEWSLETTER))
    crons = [i for i, line in enumerate(code) if line.strip().startswith("- cron:")]
    assert [code[i].strip() for i in crons] == [f'- cron: "{c}"' for c in [TEST_CRON, *SEND_CRONS]]
    for i in crons:
        assert code[i + 1].strip() == 'timezone: "Asia/Seoul"'
        assert not code[i].split('"')[1].startswith("0 ")
    assert sum("timezone:" in line for line in code) == 4


def test_mode_mapping_sends_only_on_the_send_crons():
    text = _text(NEWSLETTER)
    run_header, _ = _jobs(text)["run"]
    mode = [ln.strip() for ln in _code(run_header) if ln.strip().startswith("MODE:")]
    assert len(mode) == 1
    listed = re.search(r"fromJSON\('(\[[^']+\])'\)", mode[0]).group(1)
    assert json.loads(listed) == SEND_CRONS == [c.split('"')[1] for c in _cron_lines(text)[1:]]
    assert TEST_CRON not in mode[0]
    assert mode[0].endswith("&& 'send' || 'test') || inputs.mode }}")
    backup = [ln.strip() for ln in _code(run_header) if ln.strip().startswith("BACKUP_RUN:")]
    expected = (
        "BACKUP_RUN: ${{ github.event_name == 'schedule' && "
        "github.event.schedule != '17 8 * * 1' && 'true' || '' }}"
    )
    assert backup == [expected]


def test_send_paused_only_in_deliver_and_schedule_only():
    text = _text(NEWSLETTER)
    _, blocks = _split(text)
    deliver = _named(blocks, "Deliver")
    line = "SEND_PAUSED: ${{ github.event_name == 'schedule' && vars.SEND_PAUSED || '' }}"
    assert line in deliver
    code = _code(text)
    assert [ln.strip() for ln in code if "vars." in ln] == [line]
    assert sum("SEND_PAUSED" in ln for ln in code) == 1


def test_deliver_outcome_is_a_run_job_output():
    text = _text(NEWSLETTER)
    run_header, blocks = _jobs(text)["run"]
    assert "    outputs:\n      mode: ${{ env.MODE }}\n" in run_header
    assert "      outcome: ${{ steps.deliver.outputs.outcome }}" in run_header
    assert "        id: deliver\n" in _named(blocks, "Deliver")
    trigger = _named(blocks, "Trigger")
    assert "SCHEDULE_CRON: ${{ github.event.schedule }}" in trigger
    assert "secrets." not in trigger


# ------------------------------------------- queue, tip checkouts, commit path (05-01)


def test_concurrency_queues_and_never_cancels():
    # D-08, Pitfall 2 and 9: the same three lines in both workflows of the group.
    block = "concurrency:\n  group: newsletter{}\n  cancel-in-progress: false\n  queue: max"
    for path in (NEWSLETTER, IMPORT):
        header = "\n".join(_code(_workflow_header(_text(path))))
        header = re.sub(r"  #.*$", "", header, flags=re.MULTILINE)
        assert block.format("") in header, path.name
        assert not any("cancel-in-progress: true" in ln for ln in _code(_text(path)))


def test_every_checkout_uses_the_branch_tip():
    # Pitfall 1: queued runs and re-runs must see the commits made after the run started.
    blocks = [b for _, (_, job) in _jobs(_text(NEWSLETTER)).items() for b in job]
    checkouts = [b for b in blocks if "actions/checkout@" in b]
    assert len(checkouts) == 2
    for block in checkouts:
        assert "ref: ${{ github.ref }}" in block
        assert "persist-credentials: false" in block


def test_deliver_passes_allow_stale_only_for_literal_true():
    _, blocks = _split(_text(NEWSLETTER))
    deliver = _named(blocks, "Deliver")
    assert 'if [ "$ALLOW_STALE" = "true" ]; then' in deliver
    assert 'deliver --mode "$MODE" --allow-stale' in deliver
    assert deliver.count("--allow-stale") == 1
    assert "ALLOW_STALE" not in "\n".join(b for b in blocks if b != deliver)


def test_no_actions_write_and_four_crons_in_code():
    # Owner answer A3: the weekly commit is the keepalive; no re-enable step, no actions: write.
    code = _code(_text(NEWSLETTER))
    assert not any("actions: write" in line for line in code)
    assert sum("cron:" in line for line in code) == 4  # one test + three send (2026-11-09)
