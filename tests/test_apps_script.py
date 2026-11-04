"""Static checks on the Phase 4.1 Apps Script (subscribe, members, import, welcome).

node and clasp are not installed, so these read apps_script/Code.gs as text. The
owner's selfTest run in the Apps Script editor is the runtime check.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CODE_GS = ROOT / "apps_script" / "Code.gs"


def _src() -> str:
    return CODE_GS.read_text(encoding="utf-8")


def _body(name: str) -> str:
    """Body of a top-level function: from its signature to the first closing brace at column 0."""
    pattern = rf"^function {re.escape(name)}\([^)]*\) \{{(.*?)^\}}"
    m = re.search(pattern, _src(), re.MULTILINE | re.DOTALL)
    assert m, f"function {name} not found"
    return m.group(1)


# ---- Task 2: data routes ----


def test_routes_keep_phase4_order():
    body = _body("doPost")
    order = [
        "if (p.action === 'list') return list_(String(p.key || ''));",
        "p.action === 'members'",
        "p.action === 'import'",
        "p.action === 'subscribe'",
        "if (!TOKEN_RE.test(t)) return done_('링크가 올바르지 않아요.');",
    ]
    at = [body.find(s) for s in order]
    assert all(i >= 0 for i in at), dict(zip(order, at, strict=True))
    assert at == sorted(at)
    assert "return done_('구독이 해지됐어요. 다음 주부터는 메일이 가지 않아요.');" in body
    assert "record_(t, p['List-Unsubscribe'] === 'One-Click' ? 'one-click' : 'button');" in body


def test_keys_use_safeeq():
    for fn, key in (("members_", "SEND_LIST_KEY"), ("import_", "ADMIN_KEY")):
        body = _body(fn)
        assert f"prop_('{key}')" in body
        assert "safeEq_(" in body
        assert "!want ||" in body  # an empty property refuses every key
        assert "'forbidden'" in body


def test_members_returns_only_active_and_not_unsubscribed():
    body = _body("members_")
    assert "'active'" in body
    assert "subscribers:" in body and "version: 1" in body
    assert "ids_(" in body  # the unsubscribes ids are excluded


def test_record_deletes_subscriber_row():
    body = _body("record_")
    assert "if (!found) sh.appendRow([t, new Date().toISOString(), via]);" in body
    assert "subsSheet_()" in body
    assert "!== null" in body  # no subscribers tab: Phase 4 unsubscribe still works
    assert "deleteRow" in body
    assert body.index("appendRow") < body.index("deleteRow") < body.index("releaseLock")
    assert "matchEntireCell(true)" in body


def test_subs_sheet_may_be_missing():
    assert "getSheetByName(SUBS)" in _body("subsSheet_")


def test_import_limits():
    src = _src()
    assert "IMPORT_MAX = 25" in src
    body = _body("import_")
    for s in ("IMPORT_MAX", "'too_many'", "'bad_rows'", "Array.isArray", "JSON.parse"):
        assert s in body, s
    assert "'active'" in body and "'import', 'import'" in body  # consent_version, source
    for key in ("added", "existing", "unsubscribed", "skipped"):
        assert key in body
    assert "tokenFor_(" in body and "prop_('TOKEN_SECRET')" in body
    assert "LockService" in body
    assert "enqueueWelcome_" not in body and "Gmail" not in body


def test_schema_and_consent_version():
    src = _src()
    cols = "id email name status consent_at consent_version source created_at welcomed_at"
    quoted = ", ".join(f"'{c}'" for c in cols.split())
    assert f"const SUBS_COLS = [{quoted}];" in src
    assert "const SUBS = 'subscribers';" in src
    assert "const CONSENT_VERSIONS = ['2026-11-04'];" in src
    assert "NAME_MAX = 40" in src and "EMAIL_MAX = 254" in src
    # const SHEET stays the first const (tests/test_unsubscribe.py splits on it).
    assert src.index("const SHEET = 'unsubscribes';") == src.index("const ")


def test_email_re_mirrors_python():
    from newsletter.delivery import subscribers

    py = subscribers._EMAIL_RE.pattern.replace('\\"', '"')  # JS needs no escape for "
    assert f"const EMAIL_RE = /^{py}$/;" in _src()


def test_formula_prefix_stripped():
    norm_name = _body("normName_")
    assert "/^[=+\\-@\\s]+/" in norm_name
    assert "NAME_MAX" in norm_name
    norm_email = _body("normEmail_")
    assert "/^[=+\\-@]/" in norm_email and "EMAIL_MAX" in norm_email
    assert "EMAIL_RE.test(" in norm_email
    setup = _body("setup")
    assert "getRange('A:I').setNumberFormat('@')" in setup
    assert "getRange('A:A').setNumberFormat('@')" in setup
    assert "SUBS_COLS" in setup


def test_no_new_logging_or_pii_in_replies():
    src = _src()
    assert src.count("Logger.log") == 1
    assert "console." not in src
    for fn in ("members_", "import_"):
        body = _body(fn)
        assert "err.message" not in body and "String(err" not in body
