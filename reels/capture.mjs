// Render reels/player.html frame by frame in the installed Chrome (DevTools protocol, no npm deps)
// and encode to MP4 with the ffmpeg binary from Python's imageio-ffmpeg.
//
// Usage: node reels/capture.mjs 2026-W44 [--frames N]
// Output: reels/<week>/reel-<week>-motion.mp4  (never touches reel-<week>.mp4 or frames/)
// Env:    CHROME_PATH to override Chrome; REEL_BLOCK_FONTS=1 blocks Google Fonts (tests the font check)

import http from 'node:http';
import { spawn, execFileSync } from 'node:child_process';
import { readFile, mkdtemp, rm } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.dirname(fileURLToPath(import.meta.url));
const CALL_TIMEOUT_MS = 30000;
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

// Everything that must be torn down lives here; cleanup() is safe to call more than once.
const res = { server: null, chrome: null, ws: null, ff: null, profile: null };
let cleaned = false;
async function cleanup() {
  if (cleaned) return; cleaned = true;
  try { res.ws?.close(); } catch {}
  try { res.ff?.stdin.destroy(); res.ff?.kill(); } catch {}
  try { res.chrome?.kill(); } catch {}
  try { res.server?.close(); } catch {}
  if (res.profile) { await new Promise(r => setTimeout(r, 500)); await rm(res.profile, { recursive: true, force: true }).catch(() => {}); }
}
process.on('SIGINT', () => { console.error('interrupted'); cleanup().finally(() => process.exit(130)); });

class Fail extends Error {}
let code = 0;
try {
  const FFMPEG = (() => {
    try { return execFileSync('python', ['-c', 'import imageio_ffmpeg;print(imageio_ffmpeg.get_ffmpeg_exe())']).toString().trim(); }
    catch { throw new Fail('ffmpeg not found: run `python -m pip install imageio-ffmpeg`'); }
  })();

  // --- static server for reels/ -----------------------------------------------
  const TYPES = { '.html': 'text/html; charset=utf-8', '.json': 'application/json', '.png': 'image/png', '.js': 'text/javascript', '.mjs': 'text/javascript' };
  res.server = http.createServer(async (req, out) => {
    const rel = decodeURIComponent(new URL(req.url, 'http://x').pathname).replace(/^\/+/, '');
    const file = path.resolve(ROOT, rel || 'player.html');
    if (!file.startsWith(ROOT)) { out.writeHead(403).end(); return; }
    try { const body = await readFile(file); out.writeHead(200, { 'content-type': TYPES[path.extname(file)] || 'application/octet-stream' }).end(body); }
    catch { out.writeHead(404).end(); }
  });
  await new Promise(r => res.server.listen(0, '127.0.0.1', r));
  const port = res.server.address().port;

  // --- Chrome + DevTools protocol ---------------------------------------------
  res.profile = await mkdtemp(path.join(tmpdir(), 'reel-chrome-'));
  res.chrome = spawn(CHROME, ['--headless=new', '--remote-debugging-port=0', `--user-data-dir=${res.profile}`, '--no-first-run',
    '--no-default-browser-check', '--hide-scrollbars', '--force-device-scale-factor=1', '--window-size=1080,1920', 'about:blank'],
    { stdio: ['ignore', 'ignore', 'pipe'] });
  const wsUrl = await new Promise((resolve, reject) => {
    let buf = '';
    res.chrome.stderr.on('data', d => { buf += d; const m = buf.match(/DevTools listening on (ws:\/\/\S+)/); if (m) resolve(m[1]); });
    res.chrome.on('exit', c => reject(new Fail('chrome exited early (' + c + ')')));
    setTimeout(() => reject(new Fail('chrome did not start within 20s')), 20000);
  });

  res.ws = new WebSocket(wsUrl);
  await new Promise((r, j) => { res.ws.onopen = r; res.ws.onerror = () => j(new Fail('could not connect to chrome')); });
  let nextId = 1; const pending = new Map();
  res.ws.onmessage = ev => {
    const m = JSON.parse(ev.data);
    if (m.id && pending.has(m.id)) { const p = pending.get(m.id); pending.delete(m.id); clearTimeout(p.t); m.error ? p.reject(new Error(m.error.message)) : p.resolve(m.result); }
  };
  res.ws.onclose = () => { for (const p of pending.values()) { clearTimeout(p.t); p.reject(new Fail('chrome connection closed')); } pending.clear(); };
  const send = (method, params = {}, sessionId) => new Promise((resolve, reject) => {
    const id = nextId++;
    const t = setTimeout(() => { pending.delete(id); reject(new Fail(`${method} timed out after ${CALL_TIMEOUT_MS / 1000}s`)); }, CALL_TIMEOUT_MS);
    pending.set(id, { resolve, reject, t });
    res.ws.send(JSON.stringify(sessionId ? { id, method, params, sessionId } : { id, method, params }));
  });
  const { targetId } = await send('Target.createTarget', { url: 'about:blank' });
  const { sessionId } = await send('Target.attachToTarget', { targetId, flatten: true });
  const S = (m, p) => send(m, p, sessionId);
  const evaluate = async (expression, awaitPromise = false) => {
    const r = await S('Runtime.evaluate', { expression, awaitPromise, returnByValue: true });
    if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description || r.exceptionDetails.text);
    return r.result.value;
  };

  await S('Page.enable');
  if (process.env.REEL_BLOCK_FONTS === '1') { await S('Network.enable'); await S('Network.setBlockedURLs', { urls: ['*fonts.googleapis.com*', '*fonts.gstatic.com*'] }); }
  await S('Emulation.setDeviceMetricsOverride', { width: 1080, height: 1920, deviceScaleFactor: 1, mobile: false });
  await S('Page.navigate', { url: `http://127.0.0.1:${port}/player.html?week=${week}&capture=1` });
  for (let i = 0; ; i++) {
    if (await evaluate('window.__ready === true').catch(() => false)) break;
    if (i > 300) throw new Fail('player not ready after 60s');
    await new Promise(r => setTimeout(r, 200));
  }
  const errors = await evaluate('window.__errors');
  if (errors.length) throw new Fail('reel.json errors:\n  ' + errors.join('\n  '));
  if (!(await evaluate('window.__fontOk === true'))) throw new Fail('IBM Plex Sans KR did not load (offline or blocked?); refusing to render with a fallback font');
  const total = Math.min(await evaluate('window.__total'), limit);

  const out = path.join(ROOT, week, `reel-${week}-motion.mp4`);
  res.ff = spawn(FFMPEG, ['-y', '-loglevel', 'error', '-f', 'image2pipe', '-framerate', '30', '-c:v', 'png', '-i', '-',
    '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '18', '-preset', 'medium', '-r', '30', '-movflags', '+faststart', out],
    { stdio: ['pipe', 'inherit', 'inherit'] });
  let ffExit = null, ffErr = null;
  const ffDone = new Promise(r => res.ff.on('exit', c => { ffExit = c; r(c); }));
  res.ff.stdin.on('error', e => { ffErr = e; });
  const write = async buf => {
    if (ffExit !== null || ffErr) throw new Fail('ffmpeg stopped early (' + (ffErr?.message || 'exit ' + ffExit) + ')');
    if (!res.ff.stdin.write(buf)) await Promise.race([new Promise(r => res.ff.stdin.once('drain', r)), ffDone]);
  };

  const t0 = Date.now();
  for (let f = 0; f < total; f++) {
    await evaluate(`window.__seek(${f}), new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))`, true);
    const { data } = await S('Page.captureScreenshot', { format: 'png', clip: { x: 0, y: 0, width: 1080, height: 1920, scale: 1 }, captureBeyondViewport: false });
    await write(Buffer.from(data, 'base64'));
    if (f % 150 === 0 || f === total - 1) console.log(`frame ${f + 1}/${total}  ${((Date.now() - t0) / 1000).toFixed(0)}s`);
  }
  res.ff.stdin.end();
  const ffCode = await ffDone;
  if (ffCode !== 0) throw new Fail('ffmpeg exited ' + ffCode);
  console.log('wrote ' + path.relative(process.cwd(), out));
} catch (e) {
  console.error(e instanceof Fail ? e.message : (e.stack || e));
  code = 1;
} finally {
  await cleanup();
  process.exit(code);
}
