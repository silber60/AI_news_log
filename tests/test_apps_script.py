"""Static checks on the Phase 4.1 Apps Script (subscribe, members, import, welcome).

node and clasp are not installed, so these read apps_script/Code.gs as text. The
owner's selfTest run in the Apps Script editor is the runtime check.
"""

import re
from pathlib import Path

import pytest

from newsletter.stages import humanize

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


# ---- Task 3: subscribe, the welcome queue and the trigger ----

REPLY_MESSAGES = {
    "ok": "신청됐어요. 곧 환영 메일이 가요. 받은편지함에 없으면 스팸함도 확인해 주세요.",
    "invalid": "이메일 주소를 다시 확인해 주세요.",
    "consent": "개인정보 수집에 동의해야 신청할 수 있어요.",
    "busy": "잠시 후 다시 신청해 주세요.",
}


def test_subscribe_reply_codes_are_input_only():
    body = _body("subscribe_")
    codes = set(re.findall(r"reply_\(p\.fmt, '(\w+)'\)", body))
    assert codes == {"ok", "invalid", "consent", "busy"}
    assert "ok_first" not in _src() and "이미 구독" not in _src()
    for banned in ("Gmail", "UrlFetchApp", "sendWelcome_", "processWelcomeQueue"):
        assert banned not in body, banned
    # Every return goes through reply_, so the reply never carries row data.
    returns = re.findall(r"return ([^;]+);", body)
    assert returns and all(r.startswith("reply_(p.fmt, '") for r in returns), returns


def test_reply_shape():
    body = _body("reply_")
    assert "fmt === 'json'" in body
    assert "json_({ ok: code === 'ok', code: code })" in body
    assert "done_(" in body
    src = _src()
    for code, msg in REPLY_MESSAGES.items():
        assert f"{code}: '{msg}'" in src, code


def test_subscribe_guards():
    src = _src()
    for s in (
        "WELCOME_DAILY_CAP = 50",
        "PER_ID_LIMIT = 3",
        "GLOBAL_HOURLY_LIMIT = 30",
        "21600",
        "3600",
    ):
        assert s in src, s
    body = _body("subscribe_")
    assert "p.website" in body  # honeypot
    assert "normEmail_(" in body and "CONSENT_VERSIONS.indexOf(" in body
    assert "p.consent !== 'yes'" in body
    assert "'rl:all" in body and "'rl:' + t" in body
    assert "GLOBAL_HOURLY_LIMIT" in body and "PER_ID_LIMIT" in body
    assert "LockService" in body and "releaseLock" in body
    # The order of checks: honeypot, email, consent, global limit, per-id limit, lock.
    at = [body.index(s) for s in ("p.website", "normEmail_(", "p.consent", "rl:all", "'rl:' + t")]
    assert at == sorted(at)
    assert at[-1] < body.index("LockService")
    upsert = _body("upsert_")
    assert "find_(" in upsert and "'active'" in upsert and "'form'" in upsert
    assert "deleteRow" in upsert  # D-07: re-subscribe clears the opt-out
    assert upsert.count("enqueueWelcome_(t)") == 2  # new and reactivated only


def test_queue_holds_ids_only():
    body = _body("enqueueWelcome_")
    for prefix in ("'q_' + t", "'w_' + t", "'wd_' + day"):
        assert prefix in body, prefix
    assert "Utilities.formatDate(" in body and "'Asia/Seoul'" in body and "'yyyyMMdd'" in body
    assert "WELCOME_DAILY_CAP" in body and "WELCOME_GAP_MS" in body
    assert "email" not in body and "name" not in body
    assert "deleteProperty" in body  # prunes old w_ and wd_ entries
    assert "function enqueueWelcome_(t)" in _src()


def test_trigger_installed_idempotently():
    body = _body("installTrigger_")
    get = body.index("ScriptApp.getProjectTriggers()")
    new = body.index(
        "ScriptApp.newTrigger('processWelcomeQueue').timeBased().everyMinutes(1).create()"
    )
    assert get < new
    assert "getHandlerFunction() === 'processWelcomeQueue'" in body
    assert "installTrigger_()" in _body("setup")
    assert _src().count("everyMinutes(1)") == 1


def test_queue_worker_exists_and_returns_when_idle():
    body = _body("processWelcomeQueue")
    assert "some(queued_)" in body
    assert "k.indexOf('q_') === 0" in _body("queued_")
    idle = body.index("return;")
    assert idle < body.index("LockService")


@pytest.mark.parametrize("code", sorted(REPLY_MESSAGES))
def test_new_korean_messages_pass_humanizer(code):
    sentence = REPLY_MESSAGES[code]
    assert sentence in _src()
    codes = humanize.lint(sentence)
    assert not [c for c in codes if c in humanize.HARD_CODES], codes


# ---- Task 4: the queue worker, the welcome sender, manifest and README ----

MANIFEST = ROOT / "apps_script" / "appsscript.json"
README = ROOT / "apps_script" / "README.md"
ADDRESS_RE = re.compile(r"[\w.%+-]+@[\w.-]+\.[A-Za-z]{2,}")

# Shared with newsletter.delivery.subscribers.display_name and Code.gs selfTest.
GREETING_VECTORS = (
    (" 홍길동님 ", "홍길동님", "' 홍길동님 '"),
    ("", "구독자님", "''"),
    ("<b>", "<b>님", "'<b>'"),
    ("김\t철수", "김철수님", "'김\\t철수'"),
)

# google.script.run can call any top-level function without a trailing "_".
PUBLIC_FUNCTIONS = {
    "doGet",
    "doPost",
    "unsubscribe",
    "setup",
    "selfTest",
    "processWelcomeQueue",
    "requeueUnwelcomed",
}


def test_public_functions_are_the_known_set():
    names = re.findall(r"^function (\w+)\(", _src(), re.MULTILINE)
    public = {n for n in names if not n.endswith("_")}
    assert public == PUBLIC_FUNCTIONS
    header = _src().split("const SHEET")[0]
    assert "google.script.run" in header
    for name in PUBLIC_FUNCTIONS:
        assert name in header, name
    # setup, selfTest and processWelcomeQueue hand nothing back to a caller
    # (only their own top-level returns count; inner callbacks are indented deeper).
    for name in ("setup", "selfTest", "processWelcomeQueue", "requeueUnwelcomed"):
        assert re.search(r"^  return [^;]", _body(name), re.MULTILINE) is None, name
    assert set(re.findall(r"return ([^;]+);", _body("unsubscribe"))) == {"false", "true"}


def test_welcome_uses_gmail_advanced_service():
    src = _src()
    assert src.count("Gmail.Users.Messages.send(") == 1
    assert "Utilities.base64EncodeWebSafe(mime, Utilities.Charset.UTF_8)" in src
    assert "GmailApp" not in src and "MailApp" not in src
    assert "Gmail.Users.Messages.send" in _body("sendWelcome_")


def test_welcome_headers_mirror_python():
    body = _body("sendWelcome_")
    for s in (
        "'List-Unsubscribe: <mailto:' + me + '?subject=unsubscribe>, <' + d.endpoint + '?t=' + t + '>'",
        "'List-Unsubscribe-Post: List-Unsubscribe=One-Click'",
        "multipart/alternative",
        "'Content-Transfer-Encoding: base64'",
        "'To: ' + email,",
        "'MIME-Version: 1.0'",
        "word_(String(d.subject).replace(/[\\r\\n]/g, ' '))",
        "join('\\r\\n')",
        "Utilities.getUuid()",
    ):
        assert s in body, s
    # The name only reaches the body through the greeting, never a header.
    assert "word_(name" not in body and "'To: ' + name" not in body
    assert body.index("text/plain") < body.index("text/html")
    assert "b64_(text)" in body and "b64_(html)" in body
    assert "{76}" in _body("b64_")
    # Python sends the same pair (newsletter/delivery/deliver.py, send.py).
    deliver = (ROOT / "newsletter" / "delivery" / "deliver.py").read_text(encoding="utf-8")
    send = (ROOT / "newsletter" / "delivery" / "send.py").read_text(encoding="utf-8")
    assert '"<mailto:{user}?subject=unsubscribe>"' in deliver.replace('f"', '"')
    assert '"List-Unsubscribe=One-Click"' in send


def test_word_stays_under_75_characters():
    body = _body("word_")
    assert "=?UTF-8?B?" in body and "45" in body
    # 45 UTF-8 bytes encode to 60 base64 characters; with the 12-character frame, 72.
    assert len("=?UTF-8?B?") + 60 + len("?=") <= 75


def test_fill_uses_split_join_and_checks_shape():
    body = _body("fill_")
    assert "split(" in body and ".join(" in body
    assert ".replace(" not in body  # $& in a name would be expanded by String.replace
    assert "!== 2" in body  # each slot exactly once
    assert "/^[A-Z_]+$/" in body
    src = _src()
    assert "WELCOME_MAX_BYTES = 92160" in src
    assert "const LATEST_URL = SITE + 'welcome/latest.json';" in src
    send = _body("sendWelcome_")
    assert "fill_(d.html, d.slots, escapeHtml_(g), link)" in send
    assert "fill_(d.text, d.slots, g, link)" in send
    assert "utf8Len_(html) >= WELCOME_MAX_BYTES" in send
    assert "muteHttpExceptions: true" in send and "followRedirects: true" in send
    for code in ("'fetch'", "'no_issue'", "'shape'", "'sent'"):
        assert code in send, code
    assert "d.version !== 1 || !d.issue_id" in send


def test_queue_worker_never_frees_w():
    src = _src()
    assert "WELCOME_MAX_ATTEMPTS = 3" in src
    body = _body("processWelcomeQueue")
    assert "tryLock(" in body
    assert "deleteProperty(k)" in body  # the claim
    claim = body.index("deleteProperty(k)")
    assert claim < body.index("releaseLock") < body.index("sendWelcome_(")
    assert "res === 'sent'" in body and "markWelcomed_(" in body
    assert "(res === 'fetch' || res === 'error') && j.n + 1 < WELCOME_MAX_ATTEMPTS" in body
    assert "requeue_(j.t, j.n + 1)" in body
    for fn in ("processWelcomeQueue", "requeue_", "markWelcomed_", "sendWelcome_", "member_"):
        assert "'w_'" not in _body(fn), fn
    assert "LockService" in _body("requeue_") and "'q_' + t" in _body("requeue_")
    assert "'active'" in _body("member_") and "normEmail_(" in _body("member_")


def test_greeting_port_matches_python():
    from newsletter.delivery.subscribers import display_name

    body = _body("greetingFor_")
    assert "/(?! )[\\p{C}\\p{Z}]/gu" in body  # str.isprintable: C* and Z* except ASCII space
    assert "'님'" in body and "'구독자님'" in body
    selftest = _body("selfTest")
    for raw, want, js in GREETING_VECTORS:
        assert display_name(raw) == want
        assert f"[{js}, '{want}']" in selftest, js
    assert "escapeHtml_('<b>님') === '&lt;b&gt;님'" in selftest
    for ch in ("&amp;", "&lt;", "&gt;", "&quot;", "&#39;"):
        assert ch in _body("escapeHtml_")


def test_selftest_checks_and_logs_names_only():
    body = _body("selfTest")
    assert body.count("Logger.log") == 1
    assert "Logger.log(fails.length ? 'FAIL ' + fails.join(' ') : 'PASS');" in body
    for name in ("token", "greeting", "escape", "gmail", "user", "latest", "tabs", "trigger"):
        assert f"'{name}'" in body, name
    assert "typeof Gmail !== 'undefined'" in body
    assert "LATEST_URL" in body and "processWelcomeQueue" in body


def test_manifest():
    import json

    m = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert m["timeZone"] == "Asia/Seoul"
    assert m["runtimeVersion"] == "V8"
    assert {"userSymbol": "Gmail", "serviceId": "gmail", "version": "v1"} in m["dependencies"][
        "enabledAdvancedServices"
    ]
    assert m["webapp"] == {"executeAs": "USER_DEPLOYING", "access": "ANYONE_ANONYMOUS"}
    base = "https://www.googleapis.com/auth/"
    for scope in (
        "gmail.send",
        "spreadsheets",
        "script.external_request",
        "script.scriptapp",
        "userinfo.email",
    ):
        assert base + scope in m["oauthScopes"], scope


def test_readme_combined_setup():
    text = README.read_text(encoding="utf-8")
    for s in (
        "SHEET_ID",
        "TOKEN_SECRET",
        "LIST_KEY",
        "SEND_LIST_KEY",
        "ADMIN_KEY",
        "UNSUBSCRIBE_TOKEN_SECRET",
        "UNSUBSCRIBE_LIST_KEY",
        "SUBSCRIBER_LIST_KEY",
        "SUBSCRIBE_ADMIN_KEY",
        "appsscript.json",
        "Gmail API",
        "setup",
        "selfTest",
        "트리거",
        "processWelcomeQueue",
        "1분",
        "Origin: https://silber60.github.io",
        "read -rs",
        "확인되지 않은 앱",
        "oauthScopes",
        "action=members",
        "82a671b5104273fe07992f40d81000c8",
    ):
        assert s in text, s
    assert "새 배포" in text and "새 버전" in text
    assert "붙여 넣지 않아요" in text  # never paste a key value anywhere
    found = ADDRESS_RE.findall(text)
    assert all(a.lower().endswith("@example.com") for a in found), found


def test_queue_waits_while_no_issue_is_published():
    # Owner fix 2026-11-04: a sign-up before the first send must not lose its welcome.
    body = _body("processWelcomeQueue")
    assert "if (!issuePublished_()) return;" in body
    assert body.index("issuePublished_()") < body.index("tryLock")
    assert "res === 'no_issue'" in body and "requeue_(j.t, j.n);" in body


def test_requeue_unwelcomed_is_owner_only_and_never_rewelcomes():
    body = _body("requeueUnwelcomed")
    assert "Session.getActiveUser().getEmail()" in body
    assert "if (!me || me !== Session.getEffectiveUser().getEmail()) return;" in body
    assert "String(r[8])" in body  # welcomed_at set: already welcomed, skip
    assert "'form'" in body  # import rows never get a welcome (D-06)
    assert "WELCOME_DAILY_CAP" in body
    assert "Logger.log" not in body and "Gmail." not in body
