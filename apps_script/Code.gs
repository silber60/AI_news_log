// 모닥로그 AI 리포트: unsubscribe web app (Phase 4). Phase 4.1 adds subscribe.
//
// This file is public and holds no secrets. Everything private lives in the
// script properties (프로젝트 설정 → 스크립트 속성):
//   SHEET_ID      ID of the Sheet "모닥로그 AI 리포트 구독 관리"
//   TOKEN_SECRET  same value as the GitHub Actions secret UNSUBSCRIBE_TOKEN_SECRET
//   LIST_KEY      same value as the GitHub Actions secret UNSUBSCRIBE_LIST_KEY
//
// The Sheet stores only the 32-hex id, the time and how it came in. It never
// stores an address. Nothing here logs ids, keys or addresses; the only log
// line is the selfTest PASS/FAIL result.
//
// GET never writes (mail scanners prefetch links). Only doPost or a button
// press through google.script.run records an id.
//
// To change this script later: 배포 → 배포 관리 → 수정 → 버전: 새 버전.
// Never 새 배포: it makes a new URL and breaks every sent email header.

const SHEET = 'unsubscribes';
const TOKEN_RE = /^[0-9a-f]{32}$/;
const SITE = 'https://silber60.github.io/AI_news_log/';
const TITLE = '구독 해지 | 모닥로그 AI 리포트';

function prop_(k) { return PropertiesService.getScriptProperties().getProperty(k); }
function sheet_() { return SpreadsheetApp.openById(prop_('SHEET_ID')).getSheetByName(SHEET); }

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
  } finally {
    lock.releaseLock();
  }
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

function done_(msg) {
  const tpl = HtmlService.createTemplate(DONE_HTML);
  tpl.msg = msg;
  tpl.site = SITE;
  return tpl.evaluate().setTitle(TITLE);
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
