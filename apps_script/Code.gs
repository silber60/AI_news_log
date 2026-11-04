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
// google.script.run lets any visitor of the doGet page call any top-level
// function whose name has no trailing underscore, and it runs as the owner.
// Those public functions are doGet, doPost, unsubscribe, setup, selfTest,
// processWelcomeQueue and requeueUnwelcomed. Each is safe to call that way:
// idempotent, and none returns a key, member data or an address.
// requeueUnwelcomed also does nothing unless the owner runs it in the editor.
// Every other function ends in "_".
// tests/test_apps_script.py pins this list, so add a public one only on purpose.
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
const WELCOME_MAX_ATTEMPTS = 3;         // trigger runs that may try one welcome
const WELCOME_BATCH = 20;               // welcomes claimed per trigger run
const WELCOME_MAX_BYTES = 92160;        // the filled html must stay below this (D-04)
const LATEST_URL = SITE + 'welcome/latest.json';
const BRAND = '모닥로그 AI 리포트';
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

// Time-driven, every minute (D-04). Idle runs return at once, so they stay
// cheap against the trigger runtime quota. Under the lock each queued id is
// claimed by deleting q_<id> before anything is sent, so a welcome goes out at
// most once even when two runs overlap. Only a fetch or Gmail error re-adds
// q_<id>, at most WELCOME_MAX_ATTEMPTS runs in all. This function never deletes
// or rewrites w_<id>: no outcome (sent, no_issue, shape, gone, failed) lets a
// second welcome happen sooner than the 24 h rule allows. A reader whose
// welcome is dropped (shape, gone, failed) stays registered and gets the
// Monday mail.
function processWelcomeQueue() {
  const props = PropertiesService.getScriptProperties();
  if (!Object.keys(props.getProperties()).some(queued_)) return;
  // No issue published yet (or Pages still serves the old null file): keep the
  // queue untouched and try again next minute. One fetch per run, not per id.
  if (!issuePublished_()) return;
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(1000)) return;
  const jobs = [];
  try {
    const all = props.getProperties();
    Object.keys(all).filter(queued_).slice(0, WELCOME_BATCH).forEach(function (k) {
      jobs.push({ t: k.slice(2), n: Number(all[k]) || 0 });
      props.deleteProperty(k);
    });
  } finally {
    lock.releaseLock();
  }
  jobs.forEach(function (j) {
    let res;
    try {
      const m = TOKEN_RE.test(j.t) ? member_(j.t) : null;
      res = m ? sendWelcome_(m.email, m.name, j.t) : 'gone';
    } catch (err) {
      res = 'error';                    // a Gmail or Sheet error; nothing of it is kept
    }
    if (res === 'sent') {
      markWelcomed_(j.t);
    } else if (res === 'no_issue') {
      requeue_(j.t, j.n);               // wait for the first issue; not a failure
    } else if ((res === 'fetch' || res === 'error') && j.n + 1 < WELCOME_MAX_ATTEMPTS) {
      requeue_(j.t, j.n + 1);
    }
  });
}

function queued_(k) { return k.indexOf('q_') === 0; }

function issuePublished_() {
  try {
    const r = UrlFetchApp.fetch(LATEST_URL, { muteHttpExceptions: true, followRedirects: true });
    if (r.getResponseCode() !== 200) return true;   // let sendWelcome_ count it as a fetch error
    const d = JSON.parse(r.getContentText('UTF-8'));
    return !!(d && d.version === 1 && d.issue_id);
  } catch (err) {
    return true;
  }
}

// Owner-only, run once from the editor: queues a welcome for every active
// form sign-up that never got one (empty welcomed_at), e.g. readers who signed
// up before the first issue was published and whose welcome was dropped by the
// old worker. It ignores the 24 h gap (no welcome was ever sent to them) but
// keeps the daily cap. A visitor calling it through google.script.run has no
// active user, so it does nothing then. Returns nothing.
function requeueUnwelcomed() {
  const me = Session.getActiveUser().getEmail();
  if (!me || me !== Session.getEffectiveUser().getEmail()) return;
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(10000)) return;
  try {
    const sh = subsSheet_();
    if (!sh || sh.getLastRow() < 2) return;
    const rows = sh.getRange(2, 1, sh.getLastRow() - 1, SUBS_COLS.length).getValues();
    const props = PropertiesService.getScriptProperties();
    const all = props.getProperties();
    const day = Utilities.formatDate(new Date(), 'Asia/Seoul', 'yyyyMMdd');
    let today = Number(all['wd_' + day]) || 0;
    const set = {};
    rows.forEach(function (r) {
      const t = String(r[0]);
      if (!TOKEN_RE.test(t) || String(r[3]) !== 'active' || String(r[6]) !== 'form') return;
      if (String(r[8]) || all['q_' + t] !== undefined || today >= WELCOME_DAILY_CAP) return;
      set['q_' + t] = '0';
      set['w_' + t] = String(Date.now());
      today += 1;
    });
    set['wd_' + day] = String(today);
    props.setProperties(set);
  } finally {
    lock.releaseLock();
  }
}

function requeue_(t, n) {
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(10000)) return;     // dropped; the Monday mail still reaches the reader
  try {
    PropertiesService.getScriptProperties().setProperty('q_' + t, String(n));
  } finally {
    lock.releaseLock();
  }
}

function markWelcomed_(t) {
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(10000)) return;
  try {
    const sh = subsSheet_();
    const hit = sh && find_(sh, t);
    if (hit) {
      sh.getRange(hit.getRow(), SUBS_COLS.indexOf('welcomed_at') + 1)
          .setValue(new Date().toISOString());
    }
  } finally {
    lock.releaseLock();
  }
}

// {email, name} of the active row for id t, or null when it is gone.
function member_(t) {
  const sh = subsSheet_();
  const hit = sh && find_(sh, t);
  if (!hit) return null;
  const r = sh.getRange(hit.getRow(), 1, 1, SUBS_COLS.length).getValues()[0];
  const email = normEmail_(r[1]);
  if (!email || String(r[3]) !== 'active') return null;
  return { email: email, name: String(r[2]) };
}

// D-03, D-04: fills the render.py welcome from latest.json and sends it through
// the Gmail advanced service, the only path that keeps List-Unsubscribe. The
// headers mirror newsletter/delivery/send.py. Returns sent, fetch, no_issue or
// shape; a Gmail error throws.
function sendWelcome_(email, name, t) {
  let r;
  try {
    r = UrlFetchApp.fetch(LATEST_URL, { muteHttpExceptions: true, followRedirects: true });
  } catch (err) {
    return 'fetch';
  }
  if (r.getResponseCode() !== 200) return 'fetch';
  let d;
  try { d = JSON.parse(r.getContentText('UTF-8')); } catch (err) { return 'shape'; }
  if (!d || d.version !== 1 || !d.issue_id) return 'no_issue';
  if (!/^https:\/\//.test(String(d.endpoint || ''))) return 'shape';
  if (!/^https:\/\//.test(String(d.unsubscribe_page || ''))) return 'shape';
  const g = greetingFor_(name);
  const link = d.unsubscribe_page + t;
  const html = fill_(d.html, d.slots, escapeHtml_(g), link);
  const text = fill_(d.text, d.slots, g, link);
  if (html === null || text === null || utf8Len_(html) >= WELCOME_MAX_BYTES) return 'shape';
  const me = Session.getEffectiveUser().getEmail();
  if (!me) return 'shape';
  const b = 'b' + Utilities.getUuid().replace(/-/g, '');
  const mime = [
    'From: ' + word_(String(d.from_name || BRAND)) + ' <' + me + '>',
    'To: ' + email,                     // the address only; the name never goes in a header
    'Subject: ' + word_(String(d.subject).replace(/[\r\n]/g, ' ')),
    'MIME-Version: 1.0',
    'List-Unsubscribe: <mailto:' + me + '?subject=unsubscribe>, <' + d.endpoint + '?t=' + t + '>',
    'List-Unsubscribe-Post: List-Unsubscribe=One-Click',
    'Content-Type: multipart/alternative; boundary="' + b + '"',
    '',
    '--' + b,
    'Content-Type: text/plain; charset=UTF-8',
    'Content-Transfer-Encoding: base64',
    '',
    b64_(text),
    '--' + b,
    'Content-Type: text/html; charset=UTF-8',
    'Content-Transfer-Encoding: base64',
    '',
    b64_(html),
    '--' + b + '--',
    ''
  ].join('\r\n');
  Gmail.Users.Messages.send({ raw: Utilities.base64EncodeWebSafe(mime, Utilities.Charset.UTF_8) }, 'me');
  return 'sent';
}

// Port of newsletter/delivery/subscribers.py display_name: str.isprintable()
// rejects Unicode categories C and Z except the ASCII space.
function greetingFor_(raw) {
  let n = String(raw == null ? '' : raw).replace(/(?! )[\p{C}\p{Z}]/gu, '').trim();
  if (n.slice(-1) === '님') n = n.slice(0, -1).trim();
  return n ? n + '님' : '구독자님';
}

function escapeHtml_(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

// Fills the two slots with split/join (String.replace would expand $& in a
// name). Returns null unless each slot occurs exactly once. The link goes in
// first, so a name that spells a slot cannot add a second fill.
function fill_(src, slots, greeting, link) {
  if (typeof src !== 'string' || !slots) return null;
  const g = String(slots.greeting || '');
  const u = String(slots.unsubscribe_url || '');
  if (!/^[A-Z_]+$/.test(g) || !/^[A-Z_]+$/.test(u)) return null;
  if (src.split(g).length !== 2 || src.split(u).length !== 2) return null;
  return src.split(u).join(link).split(g).join(greeting);
}

function utf8Len_(s) {
  let n = 0;
  for (const ch of String(s)) {
    const c = ch.codePointAt(0);
    n += c < 0x80 ? 1 : c < 0x800 ? 2 : c < 0x10000 ? 3 : 4;
  }
  return n;
}

// RFC 2047 B-words of at most 45 UTF-8 bytes each (60 base64 characters, 72
// with the frame, under the 75-character limit), folded onto new lines.
function word_(s) {
  const words = [];
  let cur = '';
  let bytes = 0;
  Array.from(String(s)).forEach(function (ch) {
    const n = utf8Len_(ch);
    if (bytes + n > 45) { words.push(cur); cur = ''; bytes = 0; }
    cur += ch;
    bytes += n;
  });
  if (cur) words.push(cur);
  return words.map(function (w) {
    return '=?UTF-8?B?' + Utilities.base64Encode(w, Utilities.Charset.UTF_8) + '?=';
  }).join('\r\n ');
}

// UTF-8 base64 wrapped at 76 characters (RFC 5322 caps a line at 998).
function b64_(s) {
  return Utilities.base64Encode(s, Utilities.Charset.UTF_8).replace(/(.{76})/g, '$1\r\n');
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
  const fails = [];
  function check(name, fn) {
    let ok = false;
    try { ok = fn(); } catch (err) { ok = false; }
    if (!ok) fails.push(name);
  }
  check('token', function () {
    return tokenFor_('Subscriber@Example.com ', 'test-secret-do-not-use')
        === 'f290b8e448576cf84f63ac2b465c3e65';
  });
  const greet = [[' 홍길동님 ', '홍길동님'], ['', '구독자님'], ['<b>', '<b>님'], ['김\t철수', '김철수님']];
  check('greeting', function () {
    return greet.every(function (v) { return greetingFor_(v[0]) === v[1]; });
  });
  check('escape', function () { return escapeHtml_('<b>님') === '&lt;b&gt;님'; });
  check('gmail', function () { return typeof Gmail !== 'undefined'; });
  check('user', function () { return !!Session.getEffectiveUser().getEmail(); });
  check('latest', function () {         // issue_id null passes: nothing is published yet
    const r = UrlFetchApp.fetch(LATEST_URL, { muteHttpExceptions: true, followRedirects: true });
    if (r.getResponseCode() !== 200) return false;
    const d = JSON.parse(r.getContentText('UTF-8'));
    if (!d || d.version !== 1) return false;
    return !d.issue_id || (fill_(d.html, d.slots, 'x', 'y') !== null
        && fill_(d.text, d.slots, 'x', 'y') !== null);
  });
  check('tabs', function () {
    const ss = SpreadsheetApp.openById(prop_('SHEET_ID'));
    return !!ss.getSheetByName(SHEET) && !!ss.getSheetByName(SUBS);
  });
  check('trigger', function () {
    return ScriptApp.getProjectTriggers().some(function (tr) {
      return tr.getHandlerFunction() === 'processWelcomeQueue';
    });
  });
  Logger.log(fails.length ? 'FAIL ' + fails.join(' ') : 'PASS');
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
