// cc-routes MITM hook: transparent in-process capture shim for the
// Command Code CLI. Loaded via NODE_OPTIONS="--import hook.mjs".
//
// Why in-process: the sandbox denies TCP bind()/listen(), so a classic
// TLS-intercepting proxy cannot run here. This hook observes the same
// plaintext (pre-TLS request, post-TLS response) by wrapping
// globalThis.fetch and http/https.request. The CLI's behavior is
// unchanged: requests pass through untouched, response bodies are only
// sampled via clone() with a byte/time cap.
//
// Log: JSONL to $CC_MITM_LOG (default ./capture.jsonl). Auth material
// is redacted before writing.

import http from 'node:http';
import https from 'node:https';

const LOG = process.env.CC_MITM_LOG || './capture.jsonl';
const fs = await import('node:fs');
// run-start is written synchronously: a fast-exiting process may never
// flush an async stream (observed under bun), losing the header.
try {
  fs.appendFileSync(LOG, JSON.stringify({
    type: 'run-start', ts: new Date().toISOString(),
    argv: process.argv.slice(1),
    pid: process.pid,
    runtime: typeof Bun !== 'undefined' ? 'bun' : 'node',
  }) + '\n');
} catch { /* unwriteable log path: continue without capture */ }
const startedAt = Date.now();
// Guard against double-load (e.g. bun --preload plus inherited
// NODE_OPTIONS=--import): wrap once per process.
const FIRST_LOAD = !globalThis.__ccHookLoaded;
globalThis.__ccHookLoaded = true;

function redactHeaders(h) {
  const out = {};
  for (const [k, v] of Object.entries(h || {})) {
    out[k] = /auth|token|api[-_]?key|cookie|secret/i.test(k) ? '***' : String(v).slice(0, 300);
  }
  return out;
}

function redactBodyPreview(s) {
  if (!s) return s;
  return s
    .replace(/("?(?:api[_-]?key|token|secret|authorization|client[_-]?secret|device[_-]?code|user[_-]?code|client[_-]?id|refresh[_-]?token|access[_-]?token)"?\s*[:=]\s*"?)([^",}\s&;]{2,})/gi, '$1***')
    .replace(/(Bearer\s+)[A-Za-z0-9._~+/-]+/g, '$1***')
    .replace(/(client_id=)[^&\s]+/gi, '$1***')
    .replace(/(code=)[^&\s]+/gi, '$1***')
    .slice(0, 2000);
}

const PID = process.pid;
function emit(rec) {
  // Synchronous append: captures are low-volume and processes may exit
  // fast (or crash, e.g. yoga TLA under node), which loses async-stream
  // tails. Correctness over throughput. pid separates CLI traffic from
  // hooked children (npm, editors) sharing the log.
  rec.t_ms = Date.now() - startedAt;
  rec.pid = PID;
  try {
    fs.appendFileSync(LOG, JSON.stringify(rec) + '\n');
  } catch { /* ignore */ }
}

function normInput(input, init) {
  try {
    if (typeof input === 'string') return { url: input, method: init?.method || 'GET' };
    if (input instanceof URL) return { url: input.href, method: init?.method || 'GET' };
    if (input && typeof input === 'object' && 'url' in input) {
      return { url: String(input.url), method: init?.method || input.method || 'GET' };
    }
  } catch { /* fall through */ }
  return { url: String(input).slice(0, 500), method: init?.method || '?' };
}

async function bodyPreview(body) {
  if (body == null) return null;
  try {
    if (typeof body === 'string') return body.slice(0, 2000);
    if (body instanceof URLSearchParams) return body.toString().slice(0, 2000);
    if (body instanceof ArrayBuffer) return `[arraybuffer ${body.byteLength}B]`;
    if (ArrayBuffer.isView(body)) return `[binary ${body.byteLength}B]`;
    return `[${Object.getPrototypeOf(body)?.constructor?.name || typeof body}]`;
  } catch {
    return '[unreadable]';
  }
}

// Sample up to CAP bytes of a cloned response without disturbing the original.
async function sampleClone(res) {
  const CAP = 65536, DEADLINE = 3000;
  const t0 = Date.now();
  const chunks = [];
  let total = 0, truncated = false;
  try {
    const c = res.clone();
    const reader = c.body ? c.body.getReader() : null;
    if (!reader) return { bytes: Number(res.headers.get('content-length')) || 0, preview: '[no body]' };
    for (;;) {
      if (Date.now() - t0 > DEADLINE || total >= CAP) { truncated = true; break; }
      const { done, value } = await reader.read();
      if (done) break;
      chunks.push(value);
      total += value.byteLength;
    }
    try { await reader.cancel(); } catch { /* ignore */ }
    const buf = Buffer.concat(chunks.map((x) => Buffer.from(x)));
    return { bytes: total + (truncated ? '+' : ''), preview: redactBodyPreview(buf.toString('utf8').slice(0, 2000)) };
  } catch (e) {
    return { bytes: -1, preview: `[sample-error ${e.message}]` };
  }
}

const origFetch = FIRST_LOAD ? globalThis.fetch : globalThis.fetch.__ccOrig || globalThis.fetch;
if (FIRST_LOAD) {
  const wrapped = async function (input, init) {
  const { url, method } = normInput(input, init);
  const reqHeaders = { ...Object.fromEntries(new Headers(init?.headers || (input?.headers ?? [])).entries()) };
  let rec;
  try {
    const prev = await bodyPreview(init?.body ?? input?.body);
    rec = {
      type: 'fetch', phase: 'request', ts: new Date().toISOString(),
      method, url, headers: redactHeaders(reqHeaders),
      bodyPreview: prev && redactBodyPreview(String(prev).slice(0, 2000)),
    };
    const res = await origFetch(input, init);
    const sample = await sampleClone(res);
    rec.phase = 'request-response';
    rec.status = res.status;
    rec.respBytes = sample.bytes;
    rec.respPreview = typeof sample.preview === 'string' ? sample.preview.slice(0, 1000) : sample.preview;
    emit(rec);
    return res;
  } catch (e) {
    emit({ type: 'fetch', phase: 'error', ts: new Date().toISOString(), method, url, error: String(e).slice(0, 300) });
    throw e;
    }
  };
  wrapped.__ccOrig = origFetch;
  globalThis.fetch = wrapped;
}

function wrapRequest(mod, proto) {
  if (!FIRST_LOAD || mod.request.__ccWrapped) return;
  mod.request.__ccWrapped = true;
  const orig = mod.request;
  mod.request = function (url, options, cb) {
    let u = url, opts = options;
    if (typeof url !== 'string' && !(url instanceof URL)) { opts = url; u = undefined; }
    if (typeof opts === 'function') { cb = opts; opts = undefined; }
    const full = (() => {
      try {
        if (typeof u === 'string' && /^https?:/.test(u)) return u;
        const host = opts?.hostname || opts?.host || 'localhost';
        const port = opts?.port ? `:${opts.port}` : '';
        const path = (typeof u === 'string' ? u : opts?.path) || '/';
        return `${proto}://${host}${port}${path}`;
      } catch { return '(unparsable)'; }
    })();
    emit({
      type: 'http.request', phase: 'request', ts: new Date().toISOString(),
      method: opts?.method || 'GET', url: full,
      headers: redactHeaders(opts?.headers || {}),
    });
    const req = orig.call(this, url, options, cb);
    req.on('response', (res) => {
      // Re-resolve host/path from the live request: some clients
      // (npm's fetch) pass options shapes the guess above misses.
      let rfull = full;
      try {
        const h = req.host || req.getHeader('host') || '';
        const p = req.path || '/';
        if (h) rfull = `${proto}//${h}${p}`;
      } catch { /* keep guess */ }
      emit({
        type: 'http.request', phase: 'response', ts: new Date().toISOString(),
        method: opts?.method || 'GET', url: rfull, status: res.statusCode,
        headers: redactHeaders(res.headers),
      });
    });
    req.on('error', (e) => {
      emit({ type: 'http.request', phase: 'error', ts: new Date().toISOString(), url: full, error: String(e).slice(0, 200) });
    });
    return req;
  };
  const origGet = mod.get;
  mod.get = function (...a) {
    const r = mod.request(...a);
    r.end();
    return r;
  };
}

wrapRequest(http, 'http:');
wrapRequest(https, 'https:');

// Subprocess spawns: the CLI shells out for updates (`npm view`), browser
// open, git, editor, etc. Log command + args (no output capture).
// Module namespaces are frozen, so patch the mutable CJS exports object.
let cp = null;
try {
  const { createRequire } = await import('node:module');
  cp = createRequire(import.meta.url)('node:child_process');
} catch {
  cp = null;
}
function spawnArgs(a) {
  try {
    return (Array.isArray(a) ? a : [a]).map((x) => String(x).slice(0, 200));
  } catch {
    return ['(unparsable)'];
  }
}
if (FIRST_LOAD && cp) {
  for (const name of ['spawn', 'spawnSync', 'execFile', 'execFileSync']) {
    try {
      const orig = cp[name];
      if (typeof orig !== 'function' || orig.__ccWrapped) continue;
      const patched = function (cmd, args, opts, ...rest) {
        emit({
          type: 'spawn', phase: 'request', ts: new Date().toISOString(),
          call: name, cmd: String(cmd).slice(0, 300),
          args: spawnArgs(args).slice(0, 12),
        });
        return orig.call(this, cmd, args, opts, ...rest);
      };
      patched.__ccWrapped = true;
      cp[name] = patched;
    } catch { /* frozen exports (bun): skip spawn logging */ }
  }
  for (const name of ['exec', 'execSync']) {
    try {
      const orig = cp[name];
      if (typeof orig !== 'function' || orig.__ccWrapped) continue;
      const patched = function (cmd, ...rest) {
        emit({
          type: 'spawn', phase: 'request', ts: new Date().toISOString(),
          call: name, cmd: String(cmd).slice(0, 500), args: [],
        });
        return orig.call(this, cmd, ...rest);
      };
      patched.__ccWrapped = true;
      cp[name] = patched;
    } catch { /* frozen exports (bun): skip spawn logging */ }
  }
}
