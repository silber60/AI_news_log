// Runs the pure <script id="core"> block of reels/player.html in a vm and checks ReelCore.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const root = new URL('../', import.meta.url);
const html = readFileSync(new URL('player.html', root), 'utf8');
const m = html.match(/<script id="core">([\s\S]*?)<\/script>/);
if (!m) throw new Error('player.html has no <script id="core">');
const ctx = {};
vm.runInNewContext(m[1], ctx);
const C = ctx.ReelCore;
const W44 = JSON.parse(readFileSync(new URL('2026-W44/reel.json', root), 'utf8'));
const clone = o => JSON.parse(JSON.stringify(o));

test('bezier ends and midpoint', () => {
  const e = C.bezier(0.65, 0, 0.35, 1);
  assert.equal(e(0), 0); assert.equal(e(1), 1);
  assert.ok(Math.abs(e(0.5) - 0.5) < 1e-4);
});
test('W44 is valid', () => assert.deepEqual([...C.validate(W44)], []));
test('seconds must sum to 60', () => {
  const r = clone(W44); r.sections[0].seconds = 5;
  assert.match(C.validate(r).join(), /60/);
});
test('unknown template and panel count', () => {
  const r = clone(W44); r.sections[1].panels[0].template = 'nope'; r.sections[2].panels = [];
  const e = C.validate(r).join();
  assert.match(e, /nope/); assert.match(e, /panel/);
});
test('section starts', () => {
  const tl = C.buildTimeline(W44);
  assert.equal(tl.total, 1800);
  assert.deepEqual([...tl.sections.map(s => s.start)], [0, 120, 510, 900, 1290, 1470, 1650]);
});
test('model section panel arrivals', () => {
  const s = C.buildTimeline(W44).sections[1];
  assert.deepEqual([...s.panels.map(p => p.arrive)], [150, 276, 402]);
});
test('captions follow panels', () => {
  const tl = C.buildTimeline(W44);
  assert.equal(C.captionAt(tl, 200).cur.ko, '긴 추론 학습은 흔들려요');
  assert.equal(C.captionAt(tl, 290).cur.ko, 'Critic이 점수를 매겨 잡아 줘요');
});
test('caption at override', () => {
  const s = C.buildTimeline(W44).sections[4];
  assert.equal(s.captions[1].start, 1290 + 90);
});
test('no blur while resting, blur while moving', () => {
  const tl = C.buildTimeline(W44);
  assert.deepEqual({ ...C.blurAt(tl, 200) }, { bx: 0, by: 0 });
  assert.ok(C.blurAt(tl, 264).bx > 0);
});

test('captions without at on a later panel use that panel window', () => {
  const r = clone(W44);
  const p2 = r.sections[1].panels[1]; delete p2.caption;
  p2.captions = [{ ko: '가', en: 'a' }, { ko: '나', en: 'b' }];
  const s = C.buildTimeline(r).sections[1];
  assert.deepEqual([...s.captions.map(c => c.start)], [120, 264, 327, 390]);
  assert.deepEqual([...C.validate(r)], []);
});
test('caption at must be inside its section', () => {
  const r = clone(W44); r.sections[4].panels[0].captions[1].at = 7;
  assert.match(C.validate(r).join(), /at/);
});
test('captions must stay up at least 2 seconds', () => {
  const r = clone(W44); r.sections[4].panels[0].captions[1].at = 5.5;
  assert.match(C.validate(r).join(), /2s/);
});
test('section too short for its panels', () => {
  const r = clone(W44); r.sections[1].seconds = 2; r.sections[2].seconds = 24;
  assert.match(C.validate(r).join(), /too short/);
});
