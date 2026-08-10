import { test } from 'node:test';
import assert from 'node:assert/strict';
import worker, { timingSafeEqual, checkAuth } from '../src/index.ts';

const API_KEY = 'test-echo-backup-coordinator-key-7c1e';

function fakeKv() {
  const store = new Map();
  return {
    async get(k) { return store.has(k) ? store.get(k) : null; },
    async put(k, v) { store.set(k, v); },
  };
}

function fakeStmtChain() {
  const chain = {
    bind: (..._args) => chain,
    all: async () => ({ results: [] }),
    first: async () => null,
    run: async () => ({ meta: { last_row_id: 1, changes: 0 } }),
  };
  return chain;
}

function fakeDb() {
  return {
    prepare(_sql) { return fakeStmtChain(); },
    async batch(_stmts) { return []; },
  };
}

function fakeR2() {
  return {
    async head(_key) { return null; },
    async put(_key, _data, _opts) { return {}; },
    async get(_key) { return null; },
    async delete(_key) {},
    async list(_opts) { return { objects: [], truncated: false }; },
  };
}

function fakeFetcher() {
  return { fetch: async () => new Response(JSON.stringify({ ok: true }), { headers: { 'Content-Type': 'application/json' } }) };
}

function env() {
  return {
    DB: fakeDb(),
    CACHE: fakeKv(),
    BACKUPS: fakeR2(),
    SHARED_BRAIN: fakeFetcher(),
    SWARM_BRAIN: fakeFetcher(),
    WORKER_VERSION: '1.0.0-test',
    ECHO_API_KEY: API_KEY,
  };
}

const ctx = { waitUntil: () => {} };

// ---- timingSafeEqual / checkAuth unit tests ----

test('timingSafeEqual: equal strings match', () => {
  assert.equal(timingSafeEqual('abc123', 'abc123'), true);
});

test('timingSafeEqual: different strings do not match', () => {
  assert.equal(timingSafeEqual('abc123', 'abc124'), false);
});

test('timingSafeEqual: different-length strings do not match', () => {
  assert.equal(timingSafeEqual('short', 'a-much-longer-string'), false);
});

test('checkAuth: rejects when env has no configured key', () => {
  const e = env(); e.ECHO_API_KEY = '';
  const req = new Request('https://x/stats', { headers: { 'X-Echo-API-Key': 'anything' } });
  assert.equal(checkAuth(req, e), false);
});

test('checkAuth: accepts a correct X-Echo-API-Key header', () => {
  const req = new Request('https://x/stats', { headers: { 'X-Echo-API-Key': API_KEY } });
  assert.equal(checkAuth(req, env()), true);
});

// ---- public routes ----

test('GET / is public and returns the plain service-info JSON (not the dashboard)', async () => {
  const req = new Request('https://x/');
  const res = await worker.fetch(req, env(), ctx);
  assert.equal(res.status, 200);
  const body = await res.json();
  assert.equal(body.service, 'echo-backup-coordinator');
  assert.equal(body.status, 'operational');
});

test('GET /health is public, no key required', async () => {
  const req = new Request('https://x/health');
  const res = await worker.fetch(req, env(), ctx);
  assert.equal(res.status, 200);
  const body = await res.json();
  assert.equal(body.service, 'echo-backup-coordinator');
});

test('OPTIONS is public (CORS preflight)', async () => {
  const req = new Request('https://x/stats', { method: 'OPTIONS' });
  const res = await worker.fetch(req, env(), ctx);
  assert.equal(res.status, 204);
});

// ---- the dashboard-reachability regression guard ----

test('GET /dashboard with no credentials is 401', async () => {
  const req = new Request('https://x/dashboard');
  const res = await worker.fetch(req, env(), ctx);
  assert.equal(res.status, 401);
});

test('GET /dashboard with a valid key returns the real HTML dashboard (was previously unreachable dead code)', async () => {
  const req = new Request('https://x/dashboard', { headers: { 'X-Echo-API-Key': API_KEY } });
  const res = await worker.fetch(req, env(), ctx);
  assert.equal(res.status, 200);
  assert.equal(res.headers.get('Content-Type'), 'text/html');
  const html = await res.text();
  assert.ok(html.includes('ECHO Backup Coordinator'));
  assert.ok(html.includes('Recent Backup Jobs'));
});

test('GET / never serves the dashboard HTML, even with a valid key (root stays the plain JSON contract)', async () => {
  const req = new Request('https://x/', { headers: { 'X-Echo-API-Key': API_KEY } });
  const res = await worker.fetch(req, env(), ctx);
  assert.equal(res.status, 200);
  const body = await res.json();
  assert.equal(body.status, 'operational');
});

// ---- authenticated routes ----

test('GET /stats with no credentials is 401', async () => {
  const req = new Request('https://x/stats');
  const res = await worker.fetch(req, env(), ctx);
  assert.equal(res.status, 401);
});

test('GET /stats with a valid key succeeds', async () => {
  const req = new Request('https://x/stats', { headers: { 'X-Echo-API-Key': API_KEY } });
  const res = await worker.fetch(req, env(), ctx);
  assert.equal(res.status, 200);
  const body = await res.json();
  assert.equal(body.ok, true);
});

test('POST /backup/trigger with no credentials is 401', async () => {
  const req = new Request('https://x/backup/trigger', { method: 'POST', body: JSON.stringify({}) });
  const res = await worker.fetch(req, env(), ctx);
  assert.equal(res.status, 401);
});

test('POST /backup/trigger with a valid key but missing fields is a 400, not a crash', async () => {
  const req = new Request('https://x/backup/trigger', {
    method: 'POST',
    headers: { 'X-Echo-API-Key': API_KEY, 'Content-Type': 'application/json' },
    body: JSON.stringify({}),
  });
  const res = await worker.fetch(req, env(), ctx);
  assert.equal(res.status, 400);
});

test('GET /fleet with a valid key succeeds', async () => {
  const req = new Request('https://x/fleet', { headers: { 'X-Echo-API-Key': API_KEY } });
  const res = await worker.fetch(req, env(), ctx);
  assert.equal(res.status, 200);
  const body = await res.json();
  assert.ok(Array.isArray(body.fleet));
});

test('unknown route with a valid key 404s and lists /dashboard, not the old dead root claim', async () => {
  const req = new Request('https://x/nope', { headers: { 'X-Echo-API-Key': API_KEY } });
  const res = await worker.fetch(req, env(), ctx);
  assert.equal(res.status, 404);
  const body = await res.json();
  assert.ok(body.endpoints.some((e) => e.includes('/dashboard')));
});
