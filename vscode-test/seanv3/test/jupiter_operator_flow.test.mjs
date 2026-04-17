/**
 * Operator-flow integration tests for the Jupiter policy switch path.
 *
 * Why this file exists:
 * - The UI path the operator uses is "pick policy in the dashboard, then the browser POSTs
 *   /api/v1/jupiter/active-policy with the Bearer token from the Operator token panel".
 * - The reciprocal Kitchen handshake now sits directly behind that write.
 * - Unit tests are useful, but they do not prove that the real HTTP server, temp SQLite runtime,
 *   Bearer auth, and rollback path behave the same way a human operator experiences them.
 *
 * These tests therefore boot a real jupiter_web.mjs process, seed a temporary SQLite runtime DB,
 * and drive the exact HTTP call the dashboard emits. This is the closest automated proof we can
 * keep in-repo to "operate the system like the user would" without needing the full remote lab.
 */

import assert from 'node:assert';
import { once } from 'node:events';
import { mkdtempSync, rmSync } from 'node:fs';
import http from 'node:http';
import net from 'node:net';
import os from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawn } from 'node:child_process';
import { DatabaseSync } from 'node:sqlite';
import { test } from 'node:test';

import { ensurePaperAnalogSchema, setMeta } from '../paper_analog.mjs';

const __dirname = dirname(fileURLToPath(import.meta.url));
const PROJECT_DIR = resolve(__dirname, '..');
const REPO_ROOT = resolve(PROJECT_DIR, '..', '..');
const OPERATOR_TOKEN = 'operator-secret';
const KITCHEN_TOKEN = 'kitchen-secret';

function createTempRuntimeDb() {
  const tempDir = mkdtempSync(join(os.tmpdir(), 'jupiter-operator-flow-'));
  const sqlitePath = join(tempDir, 'sean_policy.db');
  const db = new DatabaseSync(sqlitePath);
  ensurePaperAnalogSchema(db);
  setMeta(db, 'jupiter_active_policy', 'jup_kitchen_mechanical_v1');
  db.close();
  return { tempDir, sqlitePath };
}

async function getFreePort() {
  const server = net.createServer();
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  const address = server.address();
  assert.ok(address && typeof address === 'object');
  const port = address.port;
  await new Promise((resolveClose) => server.close(resolveClose));
  return port;
}

async function waitForHttp(url, { timeoutMs = 5000 } = {}) {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    try {
      const res = await fetch(url);
      if (res.ok) {
        return;
      }
    } catch {
      // Server not up yet; keep polling.
    }
    await new Promise((resolveSleep) => setTimeout(resolveSleep, 100));
  }
  throw new Error(`Timed out waiting for ${url}`);
}

function startKitchenAckServer(handler) {
  const server = http.createServer(handler);
  return new Promise((resolveServer) => {
    server.listen(0, '127.0.0.1', () => {
      const address = server.address();
      assert.ok(address && typeof address === 'object');
      resolveServer({
        server,
        baseUrl: `http://127.0.0.1:${address.port}`,
      });
    });
  });
}

async function startJupiterWeb({ sqlitePath, kitchenBaseUrl, strictAck, timeoutMs }) {
  const port = await getFreePort();
  const child = spawn(process.execPath, ['--experimental-sqlite', 'jupiter_web.mjs'], {
    cwd: PROJECT_DIR,
    env: {
      ...process.env,
      SQLITE_PATH: sqlitePath,
      BLACKBOX_REPO_ROOT: REPO_ROOT,
      JUPITER_AUTH_MODE: 'none',
      JUPITER_WEB_BIND: '127.0.0.1',
      JUPITER_WEB_PORT: String(port),
      JUPITER_OPERATOR_TOKEN: OPERATOR_TOKEN,
      JUPITER_KITCHEN_CHECKIN_BASE: kitchenBaseUrl,
      JUPITER_KITCHEN_CHECKIN_TOKEN: KITCHEN_TOKEN,
      JUPITER_REQUIRE_KITCHEN_ACK: strictAck ? '1' : '0',
      JUPITER_KITCHEN_CHECKIN_TIMEOUT_MS: String(timeoutMs),
    },
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  let stderr = '';
  child.stderr.on('data', (chunk) => {
    stderr += String(chunk);
  });
  child.stdout.on('data', () => {
    // keep pipe drained for stability in tests
  });
  const baseUrl = `http://127.0.0.1:${port}`;
  try {
    await waitForHttp(`${baseUrl}/health`);
  } catch (error) {
    child.kill('SIGTERM');
    throw new Error(`${error instanceof Error ? error.message : String(error)}\n${stderr}`.trim());
  }
  return { child, baseUrl, getStderr: () => stderr };
}

async function stopChild(child) {
  if (child.exitCode !== null) {
    return;
  }
  child.kill('SIGTERM');
  try {
    await once(child, 'exit');
  } catch {
    // Process may already be gone; best-effort cleanup is enough in tests.
  }
}

test('operator can switch policy when Kitchen acknowledges the runtime change', async (t) => {
  const runtime = createTempRuntimeDb();
  const kitchen = await startKitchenAckServer(async (req, res) => {
    if (req.method !== 'POST' || req.url !== '/api/v1/renaissance/runtime-policy-checkin') {
      res.writeHead(404).end();
      return;
    }
    const chunks = [];
    for await (const chunk of req) {
      chunks.push(chunk);
    }
    const body = JSON.parse(Buffer.concat(chunks).toString('utf8'));
    assert.strictEqual(body.execution_target, 'jupiter');
    assert.strictEqual(body.active_policy, 'jup_v4');
    assert.strictEqual(req.headers.authorization, `Bearer ${KITCHEN_TOKEN}`);
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ ok: true, schema: 'runtime_policy_checkin_result_v1', reconcile_linkage: 'candidate_rebound' }));
  });
  const app = await startJupiterWeb({
    sqlitePath: runtime.sqlitePath,
    kitchenBaseUrl: kitchen.baseUrl,
    strictAck: true,
    timeoutMs: 500,
  });

  t.after(async () => {
    kitchen.server.close();
    await stopChild(app.child);
    rmSync(runtime.tempDir, { recursive: true, force: true });
  });

  const post = await fetch(`${app.baseUrl}/api/v1/jupiter/active-policy`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${OPERATOR_TOKEN}`,
    },
    body: JSON.stringify({ policy: 'jup_v4' }),
  });
  assert.strictEqual(post.status, 200);
  const postBody = await post.json();
  assert.strictEqual(postBody.ok, true);
  assert.strictEqual(postBody.active_policy, 'jup_v4');
  assert.strictEqual(postBody.kitchen_checkin.ok, true);

  const policy = await fetch(`${app.baseUrl}/api/v1/jupiter/policy`);
  const policyBody = await policy.json();
  assert.strictEqual(policyBody.active_policy, 'jup_v4');
});

test('operator strict mode rolls local runtime back if Kitchen hangs after headers', async (t) => {
  const runtime = createTempRuntimeDb();
  const kitchen = await startKitchenAckServer(async (req, res) => {
    if (req.method !== 'POST' || req.url !== '/api/v1/renaissance/runtime-policy-checkin') {
      res.writeHead(404).end();
      return;
    }
    for await (const _chunk of req) {
      // drain request body; the important part is that we never finish the response body
    }
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.write('{"ok": true');
  });
  const app = await startJupiterWeb({
    sqlitePath: runtime.sqlitePath,
    kitchenBaseUrl: kitchen.baseUrl,
    strictAck: true,
    timeoutMs: 200,
  });

  t.after(async () => {
    kitchen.server.close();
    await stopChild(app.child);
    rmSync(runtime.tempDir, { recursive: true, force: true });
  });

  const post = await fetch(`${app.baseUrl}/api/v1/jupiter/active-policy`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${OPERATOR_TOKEN}`,
    },
    body: JSON.stringify({ policy: 'jup_v4' }),
  });
  assert.strictEqual(post.status, 502);
  const postBody = await post.json();
  assert.strictEqual(postBody.ok, false);
  assert.strictEqual(postBody.error, 'kitchen_checkin_failed_runtime_rolled_back');
  assert.strictEqual(postBody.attempted_policy, 'jup_v4');
  assert.strictEqual(postBody.restored_policy, 'jup_kitchen_mechanical_v1');

  const policy = await fetch(`${app.baseUrl}/api/v1/jupiter/policy`);
  const policyBody = await policy.json();
  assert.strictEqual(policyBody.active_policy, 'jup_kitchen_mechanical_v1');
});
