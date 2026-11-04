// 모닥로그 AI 리포트: unsubscribe web app (Phase 4), plus subscribe, the member
// list, the one-time import and the welcome mail (Phase 4.1).
//
// This file is public and holds no secrets. Everything private lives in the
// script properties (프로젝트 설정 → 스크립트 속성), each paired with a GitHub
// Actions secret of the same value:
//   SHEET_ID       ID of the Sheet "모닥로그 AI 리포트 구독 관리" (no GitHub secret)
//   TOKEN_SECRET   = UNSUBSCRIBE_TOKEN_SECRET (never change it: old links die)
//   LIST_KEY       = UNSUBSCRIBE_LIST_KEY   (action=list: unsubscribed ids only)
//   SEND_LIST_KEY  = SUBSCRIBER_LIST_KEY    (action=members: names and addresses)
//   ADMIN_KEY      = SUBSCRIBE_ADMIN_KEY    (action=import: the one-time import)
//
// The unsubscribes tab stores only the 32-hex id, the time and how it came in.
// The subscribers tab holds name and address until the reader unsubscribes;
// then the row is deleted and only the id stays in unsubscribes. Nothing here
// logs ids, keys, names or addresses; the only log line is the selfTest result.
//
// GET never writes (mail scanners prefetch links). Only doPost or a button
// press through google.script.run records an id.
//
// The first deployment is the only 새 배포. To change this script later:
// 배포 → 배포 관리 → 수정 → 버전: 새 버전. A second 새 배포 makes a new URL
// and breaks every sent email header.

const SHEET = 'unsubscribes';
const TOKEN_RE = /^[0-9a-f]{32}$/;
const SITE = 'https://silber60.github.io/AI_news_log/';
const TITLE = '구독 해지 | 모닥로그 AI 리포트';
const SUBS = 'subscribers';
const SUBS_COLS = ['id', 'email', 'name', 'status', 'consent_at', 'consent_version', 'source', 'created_at', 'welcomed_at'];
const CONSENT_VERSIONS = ['2026-11-04'];  // the privacy page 시행일; add, never remove
const NAME_MAX = 40;
const EMAIL_MAX = 254;
const IMPORT_MAX = 25;
const PER_ID_LIMIT = 3;                 // form posts per address per 6 h; more are ignored
const GLOBAL_HOURLY_LIMIT = 30;         // form posts per hour overall; more get busy
const WELCOME_DAILY_CAP = 50;           // welcomes queued per KST day
const WELCOME_GAP_MS = 24 * 3600 * 1000; // at most one welcome per address per 24 h
const SUB_TITLE = '구독 신청 | 모닥로그 AI 리포트';
const REPLY = {
  ok: '신청됐어요. 매주 월요일 아침에 메일을 보내드려요.',
  invalid: '이메일 주소를 다시 확인해 주세요.',
  consent: '개인정보 수집에 동의해야 신청할 수 있어요.',
  busy: '잠시 후 다시 신청해 주세요.'
};
// Full-match port of newsletter/delivery/subscribers.py _EMAIL_RE.
const EMAIL_RE = /^[^@\s,;<>"']+@[^@\s,;<>"']+\.[^@\s,;<>"']+$/;

function prop_(k) { return PropertiesService.getScriptProperties().getProperty(k); }
function sheet_() { return SpreadsheetApp.openById(prop_('SHEET_ID')).getSheetByName(SHEET); }
function subsSheet_() {                 // null until setup() has made the tab
  return SpreadsheetApp.openById(prop_('SHEET_ID')).getSheetByName(SUBS);
}

function doGet(e) {
  const t = String((e && e.parameter && e.parameter.t) || '').toLowerCase();
  const tpl = HtmlService.createTemplate(CONFIRM_HTML);
  tpl.t = TOKEN_RE.test(t) ? t : '';
  tpl.site = SITE;
  return tpl.evaluate().setTitle(TITLE);
}

function doPost(e) {
  const p = params_(e);
  if (p.action === 'list') return list_(String(p.key || ''));
  if (p.action === 'members') return members_(String(p.key || ''));
  if (p.action === 'import') return import_(String(p.key || ''), String(p.rows || ''));
  if (p.action === 'subscribe') return subscribe_(p);
  const t = String(p.t || '').toLowerCase();
  if (!TOKEN_RE.test(t)) return done_('링크가 올바르지 않아요.');
  record_(t, p['List-Unsubscribe'] === 'One-Click' ? 'one-click' : 'button');
  return done_('구독이 해지됐어요. 다음 주부터는 메일이 가지 않아요.');
}

// Query-string params, plus the form-urlencoded body when e.parameter does not
// already carry it (whether Apps Script merges the body is not documented).
function params_(e) {
  const p = {};
  const q = (e && e.parameter) || {};
  Object.keys(q).forEach(function (k) { p[k] = q[k]; });
  if (p.action) return p;
  const body = (e && e.postData && e.postData.contents) || '';
  body.split('&').forEach(function (pair) {
    if (!pair) return;
    const i = pair.indexOf('=');
    const k = dec_(i < 0 ? pair : pair.slice(0, i));
    const v = dec_(i < 0 ? '' : pair.slice(i + 1));
    if (k !== null && v !== null && !(k in p)) p[k] = v;
  });
  return p;
}

function dec_(s) {
  try { return decodeURIComponent(s.replace(/\+/g, ' ')); } catch (err) { return null; }
}

function unsubscribe(t) {               // google.script.run target (doGet confirm page)
  t = String(t || '').toLowerCase();
  if (!TOKEN_RE.test(t)) return false;
  record_(t, 'button');
  return true;
}

function record_(t, via) {
  const lock = LockService.getScriptLock();
  lock.waitLock(10000);
  try {
    const sh = sheet_();
    const found = sh.getRange('A:A').createTextFinder(t).matchEntireCell(true).findNext();
    if (!found) sh.appendRow([t, new Date().toISOString(), via]);
    const subs = subsSheet_();          // D-05: drop the name and address, keep the id
    if (subs !== null) {
      let row = find_(subs, t);
      while (row) {
        subs.deleteRow(row.getRow());
        row = find_(subs, t);
      }
    }
  } finally {
    lock.releaseLock();
  }
}

function find_(sh, t) {                 // the row holding id t in column A, or null
  return sh.getRange('A:A').createTextFinder(t).matchEntireCell(true).findNext();
}

function ids_(sh) {                     // the valid ids in column A below the header
  const last = sh ? sh.getLastRow() : 0;
  return last < 2 ? [] : sh.getRange(2, 1, last - 1, 1).getValues()
      .map(function (r) { return String(r[0]); })
      .filter(function (v) { return TOKEN_RE.test(v); });
}

function json_(o) {
  return ContentService.createTextOutput(JSON.stringify(o))
      .setMimeType(ContentService.MimeType.JSON);
}

// Trimmed, lowercased address, or null. A leading = + - @ is refused so no
// cell starts like a formula.
function normEmail_(raw) {
  const e = String(raw || '').trim().toLowerCase();
  if (!e || e.length > EMAIL_MAX || /^[=+\-@]/.test(e) || !EMAIL_RE.test(e)) return null;
  return e;
}

// Control characters removed, leading = + - @ (and spaces) stripped, at most
// NAME_MAX characters. May be ''.
function normName_(raw) {
  const n = String(raw || '').replace(/\p{C}/gu, '').replace(/^[=+\-@\s]+/, '');
  return Array.from(n).slice(0, NAME_MAX).join('').trim();
}

// D-08: active rows whose id is not on the unsubscribe list. Behind SEND_LIST_KEY.
function members_(key) {
  const want = prop_('SEND_LIST_KEY') || '';
  if (!want || !safeEq_(key, want)) return json_({ error: 'forbidden' });
  const gone = {};
  ids_(sheet_()).forEach(function (t) { gone[t] = true; });
  const sh = subsSheet_();
  const last = sh ? sh.getLastRow() : 0;
  const rows = last < 2 ? [] : sh.getRange(2, 1, last - 1, SUBS_COLS.length).getValues();
  const out = [];
  rows.forEach(function (r) {
    const t = String(r[0]);
    if (!TOKEN_RE.test(t) || gone[t] || String(r[3]) !== 'active') return;
    out.push({ email: String(r[1]), name: String(r[2]) });
  });
  return json_({ version: 1, subscribers: out });
}

// D-06: one-time import of the old list. Behind ADMIN_KEY, at most IMPORT_MAX
// rows per call, no welcome mail. An earlier opt-out wins over the import.
function import_(key, rowsJson) {
  const want = prop_('ADMIN_KEY') || '';
  if (!want || !safeEq_(key, want)) return json_({ error: 'forbidden' });
  let rows;
  try { rows = JSON.parse(rowsJson); } catch (err) { return json_({ error: 'bad_rows' }); }
  if (!Array.isArray(rows)) return json_({ error: 'bad_rows' });
  if (rows.length > IMPORT_MAX) return json_({ error: 'too_many' });
  const secret = prop_('TOKEN_SECRET');
  const n = { added: 0, existing: 0, unsubscribed: 0, skipped: 0 };
  const lock = LockService.getScriptLock();
  lock.waitLock(10000);
  try {
    const un = sheet_();
    const sh = subsSheet_();
    rows.forEach(function (row) {
      const email = normEmail_(row && row.email);
      if (!email) { n.skipped++; return; }
      const t = tokenFor_(email, secret);
      if (find_(un, t)) { n.unsubscribed++; return; }
      if (find_(sh, t)) { n.existing++; return; }
      const now = new Date().toISOString();
      sh.appendRow([t, email, normName_(row.name), 'active', now, 'import', 'import', now, '']);
      n.added++;
    });
  } finally {
    lock.releaseLock();
  }
  return json_({ version: 1, added: n.added, existing: n.existing,
                 unsubscribed: n.unsubscribed, skipped: n.skipped });
}

// D-01, D-02, D-07. The reply code depends only on the input and on global
// state (the hourly limit, the lock), never on whether the address is already
// on the list, unsubscribed or rate-limited. No mail is sent here: the welcome
// is queued and the 1-minute trigger sends it, so the reply time says nothing
// about the address either.
function subscribe_(p) {
  if (String(p.website || '') !== '') return reply_(p.fmt, 'ok');  // honeypot: silent
  const email = normEmail_(p.email);
  if (!email) return reply_(p.fmt, 'invalid');
  const cv = String(p.cv || '');
  if (p.consent !== 'yes' || CONSENT_VERSIONS.indexOf(cv) < 0) return reply_(p.fmt, 'consent');
  const cache = CacheService.getScriptCache();
  const now = Date.now();
  if (bump_(cache, 'rl:all:' + Math.floor(now / 3600000), 3600) > GLOBAL_HOURLY_LIMIT) {
    return reply_(p.fmt, 'busy');
  }
  const t = tokenFor_(email, prop_('TOKEN_SECRET'));
  if (bump_(cache, 'rl:' + t + ':' + Math.floor(now / 21600000), 21600) > PER_ID_LIMIT) {
    return reply_(p.fmt, 'ok');          // silent, so the limit is no oracle
  }
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(10000)) return reply_(p.fmt, 'busy');
  try {
    upsert_(t, email, normName_(p.name), cv);
  } finally {
    lock.releaseLock();
  }
  return reply_(p.fmt, 'ok');
}

// Fixed-window counter in CacheService; returns the count after this post.
// Not atomic, which is fine for a rate limit.
function bump_(cache, key, ttl) {
  const n = (Number(cache.get(key)) || 0) + 1;
  cache.put(key, String(n), ttl);
  return n;
}

// Called inside the script lock. One row per id: a new address is appended, an
// unsubscribed one is reactivated (D-07), an active one only gets an empty name
// filled. Only new and reactivated addresses are queued for a welcome.
function upsert_(t, email, name, cv) {
  const sh = subsSheet_();
  const un = sheet_();
  const now = new Date().toISOString();
  const gone = find_(un, t);
  if (gone) un.deleteRow(gone.getRow());
  const hit = find_(sh, t);
  if (!hit) {
    sh.appendRow([t, email, name, 'active', now, cv, 'form', now, '']);
    enqueueWelcome_(t);
    return;
  }
  const r = hit.getRow();
  const cur = sh.getRange(r, 1, 1, SUBS_COLS.length).getValues()[0];
  if (gone || String(cur[3]) !== 'active') {
    sh.getRange(r, 2, 1, 6).setValues([[email, name || String(cur[2]), 'active', now, cv, 'form']]);
    enqueueWelcome_(t);
  } else if (name && !String(cur[2])) {
    sh.getRange(r, 3).setValue(name);
  }
}

// Called inside the script lock. Script properties hold ids and counts only:
//   q_<id>        queued welcome, value = failed attempts so far
//   w_<id>        when a welcome was last queued (ms); blocks another for 24 h
//   wd_<yyyyMMdd> welcomes queued that KST day
function enqueueWelcome_(t) {
  const props = PropertiesService.getScriptProperties();
  const all = props.getProperties();
  const now = Date.now();
  const day = Utilities.formatDate(new Date(now), 'Asia/Seoul', 'yyyyMMdd');
  const old = Utilities.formatDate(new Date(now - 2 * 86400000), 'Asia/Seoul', 'yyyyMMdd');
  Object.keys(all).forEach(function (k) {
    if (k.indexOf('w_') === 0 && now - Number(all[k]) >= WELCOME_GAP_MS) props.deleteProperty(k);
    if (k.indexOf('wd_') === 0 && k.slice(3) < old) props.deleteProperty(k);
  });
  const last = Number(all['w_' + t]) || 0;
  const today = Number(all['wd_' + day]) || 0;
  if (now - last < WELCOME_GAP_MS || today >= WELCOME_DAILY_CAP) return false;
  const set = {};
  set['q_' + t] = '0';
  set['w_' + t] = String(now);
  set['wd_' + day] = String(today + 1);
  props.setProperties(set);
  return true;
}

function reply_(fmt, code) {
  if (fmt === 'json') return json_({ ok: code === 'ok', code: code });
  return done_(REPLY[code], SUB_TITLE);
}

// Installs the 1-minute trigger for processWelcomeQueue once; setup() calls it.
function installTrigger_() {
  const has = ScriptApp.getProjectTriggers().some(function (tr) {
    return tr.getHandlerFunction() === 'processWelcomeQueue';
  });
  if (!has) ScriptApp.newTrigger('processWelcomeQueue').timeBased().everyMinutes(1).create();
}

// Time-driven, every minute. Idle runs return at once.
function processWelcomeQueue() {
  const keys = Object.keys(PropertiesService.getScriptProperties().getProperties());
  if (!keys.some(function (k) { return k.indexOf('q_') === 0; })) return;
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(1000)) return;
  lock.releaseLock();
}

function list_(key) {
  const want = prop_('LIST_KEY') || '';
  if (!want || !safeEq_(key, want)) {
    return ContentService.createTextOutput('{"error":"forbidden"}')
        .setMimeType(ContentService.MimeType.JSON);
  }
  const sh = sheet_();
  const last = sh.getLastRow();
  const ids = last < 2 ? [] : sh.getRange(2, 1, last - 1, 1).getValues()
      .map(function (r) { return String(r[0]); })
      .filter(function (v) { return TOKEN_RE.test(v); });
  return ContentService.createTextOutput(JSON.stringify({ version: 1, ids: ids }))
      .setMimeType(ContentService.MimeType.JSON);
}

function safeEq_(a, b) {                // constant-time for equal lengths
  a = String(a); b = String(b);
  if (a.length !== b.length) return false;
  let d = 0;
  for (let i = 0; i < a.length; i++) d |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return d === 0;
}

function done_(msg, title) {
  const tpl = HtmlService.createTemplate(DONE_HTML);
  tpl.msg = msg;
  tpl.site = SITE;
  return tpl.evaluate().setTitle(title || TITLE);
}

// Must match newsletter/delivery/unsubscribe.py token(): HMAC-SHA256 over
// email.strip().lower(), keyed with the secret, lowercase hex, first 32 chars.
function tokenFor_(email, secret) {
  const bytes = Utilities.computeHmacSha256Signature(
      String(email).trim().toLowerCase(), secret, Utilities.Charset.UTF_8);
  // Byte[] values are signed (-128..127); & 0xff makes them 0..255.
  return bytes.map(function (b) { return ('0' + (b & 0xff).toString(16)).slice(-2); })
      .join('').slice(0, 32);
}

function setup() {                       // owner runs once
  const ss = SpreadsheetApp.openById(prop_('SHEET_ID'));
  const sh = ss.getSheetByName(SHEET) || ss.insertSheet(SHEET);
  sh.getRange('A:A').setNumberFormat('@'); // keep ids as text ("123e45..." must not become a number)
  if (sh.getLastRow() === 0) sh.appendRow(['id', 'at', 'via']);
  const subs = ss.getSheetByName(SUBS) || ss.insertSheet(SUBS);
  subs.getRange('A:I').setNumberFormat('@');  // plain text: no formulas, no number ids
  if (subs.getLastRow() === 0) subs.appendRow(SUBS_COLS);
  installTrigger_();
}

function selfTest() {                    // owner runs once; must log PASS
  const got = tokenFor_('Subscriber@Example.com ', 'test-secret-do-not-use');
  Logger.log(got === 'f290b8e448576cf84f63ac2b465c3e65' ? 'PASS' : 'FAIL ' + got);
}

// The token sits in a quoted HTML attribute (HTML-escaped by the printing
// scriptlet) and the script reads it from there, so no scriptlet runs in a
// JavaScript context. It is regex-limited to hex either way.
const CONFIRM_HTML = '<!doctype html><html lang="ko"><head><meta charset="utf-8">'
  + '<meta name="viewport" content="width=device-width,initial-scale=1"></head>'
  + '<body style="font-family:-apple-system,BlinkMacSystemFont,\'Apple SD Gothic Neo\','
  + '\'Malgun Gothic\',sans-serif;padding:24px;color:#1f1f1f">'
  + '<? if (t) { ?><h2>구독을 해지할까요?</h2>'
  + '<button id="b" data-t="<?= t ?>" style="font-size:16px;padding:10px 20px">구독 해지</button>'
  + '<p id="m"></p>'
  + '<script>document.getElementById("b").onclick=function(){var b=this;b.disabled=true;'
  + 'google.script.run.withSuccessHandler(function(ok){document.getElementById("m").textContent='
  + 'ok?"구독이 해지됐어요. 다음 주부터는 메일이 가지 않아요.":"링크가 올바르지 않아요.";})'
  + '.withFailureHandler(function(){b.disabled=false;'
  + 'document.getElementById("m").textContent="잠시 후 다시 눌러 주세요.";})'
  + '.unsubscribe(b.getAttribute("data-t"));};</script>'
  + '<? } else { ?><p>링크가 올바르지 않아요.</p><? } ?>'
  + '<p><a href="<?= site ?>" target="_top">모닥로그 AI 리포트 홈</a></p></body></html>';

const DONE_HTML = '<!doctype html><html lang="ko"><head><meta charset="utf-8">'
  + '<meta name="viewport" content="width=device-width,initial-scale=1"></head>'
  + '<body style="font-family:-apple-system,BlinkMacSystemFont,\'Apple SD Gothic Neo\','
  + '\'Malgun Gothic\',sans-serif;padding:24px;color:#1f1f1f">'
  + '<p><?= msg ?></p><p><a href="<?= site ?>" target="_top">모닥로그 AI 리포트 홈</a></p>'
  + '</body></html>';
