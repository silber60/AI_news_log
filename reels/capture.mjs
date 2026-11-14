// Render reels/player.html frame by frame in the installed Chrome (DevTools protocol, no npm deps)
// and encode to MP4 with the ffmpeg binary from Python's imageio-ffmpeg.
//
// Usage: node reels/capture.mjs 2026-W44 [--frames N]
// Output: reels/<week>/reel-<week>-motion.mp4  (never touches reel-<week>.mp4 or frames/)

import http from 'node:http';
import { spawn, execFileSync } from 'node:child_process';
import { readFile, mkdtemp, rm } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.dirname(fileURLToPath(import.meta.url));
const week = process.argv[2];
const limitArg = process.argv.indexOf('--frames');
const limit = limitArg > 0 ? Number(process.argv[limitArg + 1]) : Infinity;
if (!week || !/^[\w-]+$/.test(week)) { console.error('usage: node reels/capture.mjs <week> [--frames N]'); process.exit(2); }
if (!existsSync(path.join(ROOT, week, 'reel.json'))) { console.error(`missing ${week}/reel.json`); process.exit(2); }

const CHROME = [
  process.env.CHROME_PATH,
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
  path.join(process.env.LOCALAPPDATA || '', 'Google/Chrome/Application/chrome.exe'),
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  '/usr/bin/google-chrome',
].find(p => p && existsSync(p));
if (!CHROME) { console.error('Chrome not found; set CHROME_PATH'); process.exit(2); }
const FFMPEG = execFileSync('python', ['-c', 'import imageio_ffmpeg;print(imageio_ffmpeg.get_ffmpeg_exe())']).toString().trim();

// --- static server for reels/ -------------------------------------------------
const TYPES = { '.html': 'text/html; charset=utf-8', '.json': 'application/json', '.png': 'image/png', '.js': 'text/javascript', '.mjs': 'text/javascript' };
const server = http.createServer(async (req, res) => {
  const rel = decodeURIComponent(new URL(req.url, 'http://x').pathname).replace(/^\/+/, '');
  const file = path.resolve(ROOT, rel || 'player.html');
  if (!file.startsWith(ROOT)) { res.writeHead(403).end(); return; }
  try { const body = await readFile(file); res.writeHead(200, { 'content-type': TYPES[path.extname(file)] || 'application/octet-stream' }).end(body); }
  catch { res.writeHead(404).end(); }
});
await new Promise(r => server.listen(0, '127.0.0.1', r));
const port = server.address().port;

// --- Chrome + DevTools protocol ------------------------------------------------
const profile = await mkdtemp(path.join(tmpdir(), 'reel-chrome-'));
const chrome = spawn(CHROME, ['--headless=new', '--remote-debugging-port=0', `--user-data-dir=${profile}`, '--no-first-run',
  '--no-default-browser-check', '--hide-scrollbars', '--force-device-scale-factor=1', '--window-size=1080,1920', 'about:blank'],
  { stdio: ['ignore', 'ignore', 'pipe'] });
const wsUrl = await new Promise((resolve, reject) => {
  let buf = '';
  chrome.stderr.on('data', d => { buf += d; const m = buf.match(/DevTools listening on (ws:\/\/\S+)/); if (m) resolve(m[1]); });
  chrome.on('exit', c => reject(new Error('chrome exited ' + c)));
  setTimeout(() => reject(new Error('chrome did not start')), 20000);
});

const ws = new WebSocket(wsUrl);
await new Promise((r, j) => { ws.onopen = r; ws.onerror = j; });
let nextId = 1; const pending = new Map();
ws.onmessage = ev => { const m = JSON.parse(ev.data); if (m.id && pending.has(m.id)) { const p = pending.get(m.id); pending.delete(m.id); m.error ? p.reject(new Error(m.error.message)) : p.resolve(m.result); } };
const send = (method, params = {}, sessionId) => new Promise((resolve, reject) => {
  const id = nextId++; pending.set(id, { resolve, reject });
  ws.send(JSON.stringify(sessionId ? { id, method, params, sessionId } : { id, method, params }));
});
const { targetId } = await send('Target.createTarget', { url: 'about:blank' });
const { sessionId } = await send('Target.attachToTarget', { targetId, flatten: true });
const S = (m, p) => send(m, p, sessionId);
const evaluate = async (expression, awaitPromise = false) => {
  const r = await S('Runtime.evaluate', { expression, awaitPromise, returnByValue: true });
  if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description || r.exceptionDetails.text);
  return r.result.value;
};

let ff, code = 0;
try {
  await S('Page.enable');
  await S('Emulation.setDeviceMetricsOverride', { width: 1080, height: 1920, deviceScaleFactor: 1, mobile: false });
  await S('Page.navigate', { url: `http://127.0.0.1:${port}/player.html?week=${week}&capture=1` });
  for (let i = 0; ; i++) {
    if (await evaluate('window.__ready === true').catch(() => false)) break;
    if (i > 300) throw new Error('player not ready after 60s');
    await new Promise(r => setTimeout(r, 200));
  }
  const errors = await evaluate('window.__errors');
  if (errors.length) { console.error('reel.json errors:\n  ' + errors.join('\n  ')); code = 1; throw null; }
  const total = Math.min(await evaluate('window.__total'), limit);

  const out = path.join(ROOT, week, `reel-${week}-motion.mp4`);
  ff = spawn(FFMPEG, ['-y', '-loglevel', 'error', '-f', 'image2pipe', '-framerate', '30', '-c:v', 'png', '-i', '-',
    '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '18', '-preset', 'medium', '-r', '30', '-movflags', '+faststart', out],
    { stdio: ['pipe', 'inherit', 'inherit'] });
  const ffDone = new Promise(r => ff.on('exit', r));
  const t0 = Date.now();
  for (let f = 0; f < total; f++) {
    await evaluate(`window.__seek(${f}), new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))`, true);
    const { data } = await S('Page.captureScreenshot', { format: 'png', clip: { x: 0, y: 0, width: 1080, height: 1920, scale: 1 }, captureBeyondViewport: false });
    const buf = Buffer.from(data, 'base64');
    if (!ff.stdin.write(buf)) await new Promise(r => ff.stdin.once('drain', r));
    if (f % 150 === 0 || f === total - 1) console.log(`frame ${f + 1}/${total}  ${((Date.now() - t0) / 1000).toFixed(0)}s`);
  }
  ff.stdin.end();
  const ffCode = await ffDone;
  if (ffCode !== 0) { code = 1; throw new Error('ffmpeg exited ' + ffCode); }
  console.log('wrote ' + path.relative(process.cwd(), out));
} catch (e) {
  if (e) { console.error(e.message || e); code = code || 1; }
  if (ff && !ff.killed) ff.stdin.destroy();
} finally {
  try { ws.close(); } catch {}
  chrome.kill();
  server.close();
  await new Promise(r => setTimeout(r, 500));
  await rm(profile, { recursive: true, force: true }).catch(() => {});
  process.exit(code);
}
