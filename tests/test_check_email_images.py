"""scripts/check_email_images.py: hosted image URL check (01.1-05)."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import httpx
import pytest
import respx

from newsletter.stages.render import ASSET_BASE_URL

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "check_email_images.py"


@pytest.fixture(scope="module")
def checker():
    spec = importlib.util.spec_from_file_location("check_email_images", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _png(status: int = 200, ctype: str = "image/png") -> httpx.Response:
    return httpx.Response(status, headers={"content-type": ctype}, content=b"\x89PNG....")


def test_fixture_srcs_are_asset_urls(checker):
    srcs = checker.collect_srcs(None)
    assert srcs
    assert all(s.startswith(ASSET_BASE_URL) for s in srcs)


def test_all_images_ok_exits_0(checker, capsys):
    srcs = checker.collect_srcs(None)
    with respx.mock(assert_all_called=True) as router:
        for src in srcs:
            router.get(src).mock(return_value=_png())
        assert checker.main([]) == 0
    out = capsys.readouterr().out
    assert f"{len(srcs)}/{len(srcs)} ok" in out


def test_one_404_exits_1(checker):
    srcs = checker.collect_srcs(None)
    with respx.mock() as router:
        for src in srcs:
            router.get(src).mock(return_value=_png())
        router.get(srcs[0]).mock(return_value=httpx.Response(404, text="nope"))
        assert checker.main([]) == 1


def test_html_200_exits_1(checker):
    srcs = checker.collect_srcs(None)
    with respx.mock() as router:
        for src in srcs:
            router.get(src).mock(return_value=_png())
        router.get(srcs[-1]).mock(return_value=_png(ctype="text/html; charset=utf-8"))
        assert checker.main([]) == 1


def test_email_html_argument_checks_every_src(checker, tmp_path):
    page = tmp_path / "email.html"
    page.write_text(
        '<img src="https://cdn-uploads.huggingface.co/x.png" alt="a">'
        f'<img src="{ASSET_BASE_URL}/otter-wave.jpg" alt="b">',
        encoding="utf-8",
    )
    assert checker.collect_srcs(str(page)) == [
        "https://cdn-uploads.huggingface.co/x.png",
        f"{ASSET_BASE_URL}/otter-wave.jpg",
    ]
    with respx.mock(assert_all_called=True) as router:
        router.get("https://cdn-uploads.huggingface.co/x.png").mock(
            return_value=_png(ctype="image/jpeg")
        )
        router.get(f"{ASSET_BASE_URL}/otter-wave.jpg").mock(return_value=_png(ctype="image/jpeg"))
        assert checker.main([str(page)]) == 0


def test_dry_run_subprocess_without_install():
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--dry-run"],
        check=False,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
    assert lines
    assert all(ln.startswith(ASSET_BASE_URL) for ln in lines)
