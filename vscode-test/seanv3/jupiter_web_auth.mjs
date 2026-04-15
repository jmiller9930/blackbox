/**
 * Session login + email password reset for jupiter-web (optional; lab).
 * Secrets: JUPITER_SESSION_SECRET, optional RESEND_API_KEY for outbound mail.
 * Single user email: JUPITER_AUTH_EMAIL (default jmiller9930@om3.us).
 */
import { createHash, createHmac, randomBytes, scryptSync, timingSafeEqual } from 'node:crypto';
import { DatabaseSync } from 'node:sqlite';

const COOKIE = 'jupiter_lab_sess';
const RESET_TABLE = 'jupiter_web_auth_reset';
const USER_TABLE = 'jupiter_web_auth_user';

/** @param {import('node:sqlite').DatabaseSync} db */
export function ensureJupiterWebAuthSchema(db) {
  db.exec(`
    CREATE TABLE IF NOT EXISTS ${USER_TABLE} (
      email TEXT PRIMARY KEY COLLATE NOCASE,
      password_scrypt BLOB NOT NULL,
      salt BLOB NOT NULL,
      updated_utc TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS ${RESET_TABLE} (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      token_hash TEXT NOT NULL UNIQUE,
      email TEXT NOT NULL COLLATE NOCASE,
      expires_utc TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_jw_reset_exp ON ${RESET_TABLE} (expires_utc);
  `);
}

export function getConfiguredAuthEmail() {
  return (process.env.JUPITER_AUTH_EMAIL || 'jmiller9930@om3.us').trim().toLowerCase();
}

export function getSessionSecret() {
  const s = (process.env.JUPITER_SESSION_SECRET || '').trim();
  if (s.length < 16) return '';
  return s;
}

export function getPublicBaseUrl() {
  const u = (process.env.JUPITER_PUBLIC_BASE_URL || '').trim().replace(/\/$/, '');
  return u || '';
}

function hashToken(token) {
  return createHash('sha256').update(String(token), 'utf8').digest('hex');
}

function hashPassword(password, salt) {
  return scryptSync(String(password), salt, 64);
}

function parseCookies(cookieHeader) {
  const out = {};
  if (!cookieHeader || typeof cookieHeader !== 'string') return out;
  for (const part of cookieHeader.split(';')) {
    const i = part.indexOf('=');
    if (i === -1) continue;
    const k = part.slice(0, i).trim();
    const v = part.slice(i + 1).trim();
    out[k] = decodeURIComponent(v);
  }
  return out;
}

function signSessionPayload(email, expSec, secret) {
  const payload = `${expSec}|${email}`;
  const sig = createHmac('sha256', secret).update(payload, 'utf8').digest('base64url');
  return Buffer.from(`${payload}|${sig}`, 'utf8').toString('base64url');
}

function verifySessionCookie(raw, secret) {
  if (!raw || !secret) return null;
  let decoded;
  try {
    decoded = Buffer.from(String(raw), 'base64url').toString('utf8');
  } catch {
    return null;
  }
  const last = decoded.lastIndexOf('|');
  if (last === -1) return null;
  const sig = decoded.slice(last + 1);
  const payload = decoded.slice(0, last);
  const payloadSig = createHmac('sha256', secret).update(payload, 'utf8').digest('base64url');
  const a = Buffer.from(sig, 'utf8');
  const b = Buffer.from(payloadSig, 'utf8');
  if (a.length !== b.length || !timingSafeEqual(a, b)) return null;
  const first = payload.indexOf('|');
  if (first === -1) return null;
  const expSec = parseInt(payload.slice(0, first), 10);
  const email = payload.slice(first + 1);
  if (!Number.isFinite(expSec) || expSec < Math.floor(Date.now() / 1000)) return null;
  return { email: email.toLowerCase(), expSec };
}

/**
 * @param {import('http').IncomingMessage} req
 * @param {string} secret
 */
export function getSessionFromRequest(req, secret) {
  const cookies = parseCookies(req.headers.cookie || '');
  const raw = cookies[COOKIE];
  return verifySessionCookie(raw, secret);
}

/**
 * @param {import('node:sqlite').DatabaseSync} db
 * @param {string} email
 * @param {string} password
 */
export function upsertUserPassword(db, email, password) {
  const salt = randomBytes(16);
  const pw = hashPassword(password, salt);
  const em = String(email).trim().toLowerCase();
  db.prepare(
    `INSERT INTO ${USER_TABLE} (email, password_scrypt, salt, updated_utc)
     VALUES (?, ?, ?, ?)
     ON CONFLICT(email) DO UPDATE SET
       password_scrypt = excluded.password_scrypt,
       salt = excluded.salt,
       updated_utc = excluded.updated_utc`
  ).run(em, pw, salt, new Date().toISOString());
}

/**
 * @param {import('node:sqlite').DatabaseSync} db
 * @param {string} email
 * @param {string} password
 */
export function verifyUserPassword(db, email, password) {
  const em = String(email).trim().toLowerCase();
  const row = db.prepare(`SELECT password_scrypt, salt FROM ${USER_TABLE} WHERE email = ?`).get(em);
  if (!row) return false;
  const got = hashPassword(password, row.salt);
  const exp = row.password_scrypt;
  if (got.length !== exp.length) return false;
  return timingSafeEqual(got, exp);
}

/**
 * Bootstrap first user from env if table empty (one-time; remove env after).
 * @param {import('node:sqlite').DatabaseSync} db
 */
export function bootstrapJupiterAuthUserIfNeeded(db) {
  const email = getConfiguredAuthEmail();
  const bootstrap =
    (process.env.JUPITER_AUTH_BOOTSTRAP_PASSWORD || process.env.JUPITER_WEB_LOGIN_PASSWORD || '').trim();
  if (!email || !bootstrap) return;
  const n = db.prepare(`SELECT COUNT(*) AS c FROM ${USER_TABLE}`).get();
  const count = n && typeof n.c === 'number' ? n.c : 0;
  if (count > 0) return;
  upsertUserPassword(db, email, bootstrap);
  console.error(
    `[jupiter-auth] bootstrapped login for ${email} from env — remove JUPITER_AUTH_BOOTSTRAP_PASSWORD / JUPITER_WEB_LOGIN_PASSWORD from the container`
  );
}

/** @param {import('http').ServerResponse} res */
export function setSessionCookie(res, email, secret) {
  const maxAgeSec = Math.max(60, Math.min(60 * 60 * 24 * 30, parseInt(process.env.JUPITER_SESSION_MAX_AGE_SEC || '604800', 10) || 604800));
  const expSec = Math.floor(Date.now() / 1000) + maxAgeSec;
  const val = signSessionPayload(email.toLowerCase(), expSec, secret);
  const secure = process.env.JUPITER_SESSION_COOKIE_SECURE === '1' ? '; Secure' : '';
  res.setHeader(
    'Set-Cookie',
    `${COOKIE}=${encodeURIComponent(val)}; Path=/; HttpOnly; SameSite=Lax; Max-Age=${maxAgeSec}${secure}`
  );
}

/** @param {import('http').ServerResponse} res */
export function clearSessionCookie(res) {
  const secure = process.env.JUPITER_SESSION_COOKIE_SECURE === '1' ? '; Secure' : '';
  res.setHeader('Set-Cookie', `${COOKIE}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0${secure}`);
}

async function sendPasswordResetEmail(to, resetUrl) {
  const key = (process.env.RESEND_API_KEY || '').trim();
  const from = (process.env.RESEND_FROM || 'Jupiter Lab <onboarding@resend.dev>').trim();
  if (!key) {
    console.error('[jupiter-auth] RESEND_API_KEY not set — password reset link (use within 1h):');
    console.error(resetUrl);
    return { ok: false, logged: true };
  }
  const r = await fetch('https://api.resend.com/emails', {
    method: 'POST',
    headers: { Authorization: `Bearer ${key}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({
      from,
      to: [to],
      subject: 'Reset your Jupiter lab password',
      html: `<p><a href="${resetUrl}">Set a new password</a></p><p>This link expires in about one hour. If you did not request a reset, ignore this email.</p><p>Forgot again? Use <strong>Forgot password</strong> on the login page to get a new link.</p>`,
    }),
  });
  const t = await r.text();
  if (!r.ok) {
    console.error('[jupiter-auth] Resend error:', r.status, t);
    return { ok: false, logged: false };
  }
  return { ok: true, logged: false };
}

function buildResetUrl(base, token) {
  const b = base || '';
  const path = `/auth/reset?token=${encodeURIComponent(token)}`;
  return b ? `${b}${path}` : path;
}

/**
 * @param {import('node:sqlite').DatabaseSync} db
 * @param {string} email
 */
export async function createResetAndEmail(db, email) {
  const allowed = getConfiguredAuthEmail();
  const em = String(email || '').trim().toLowerCase();
  const row = db.prepare(`SELECT email FROM ${USER_TABLE} WHERE email = ?`).get(allowed);
  if (em !== allowed || !row) {
    return { ok: true, generic: true };
  }
  const token = randomBytes(32).toString('hex');
  const th = hashToken(token);
  const exp = new Date(Date.now() + 60 * 60 * 1000).toISOString();
  db.prepare(`DELETE FROM ${RESET_TABLE} WHERE email = ?`).run(allowed);
  db.prepare(`INSERT INTO ${RESET_TABLE} (token_hash, email, expires_utc) VALUES (?, ?, ?)`).run(th, allowed, exp);
  const base = getPublicBaseUrl();
  const url = buildResetUrl(base, token);
  await sendPasswordResetEmail(allowed, url);
  return { ok: true, generic: true };
}

/** Read-only: token valid and not expired (does not delete). */
export function peekResetToken(db, token) {
  const th = hashToken(token);
  const row = db.prepare(`SELECT email, expires_utc FROM ${RESET_TABLE} WHERE token_hash = ?`).get(th);
  if (!row) return null;
  const exp = new Date(String(row.expires_utc)).getTime();
  if (!Number.isFinite(exp) || Date.now() > exp) {
    db.prepare(`DELETE FROM ${RESET_TABLE} WHERE token_hash = ?`).run(th);
    return null;
  }
  return String(row.email).toLowerCase();
}

/** Verify and delete token row (use on POST after password change). */
export function consumeResetToken(db, token) {
  const th = hashToken(token);
  const row = db.prepare(`SELECT email, expires_utc FROM ${RESET_TABLE} WHERE token_hash = ?`).get(th);
  if (!row) return null;
  const exp = new Date(String(row.expires_utc)).getTime();
  if (!Number.isFinite(exp) || Date.now() > exp) {
    db.prepare(`DELETE FROM ${RESET_TABLE} WHERE token_hash = ?`).run(th);
    return null;
  }
  db.prepare(`DELETE FROM ${RESET_TABLE} WHERE token_hash = ?`).run(th);
  return String(row.email).toLowerCase();
}

export function htmlEscape(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function authShell(title, bodyHtml) {
  return `<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>${htmlEscape(title)}</title>
<style>
body{margin:0;min-height:100vh;background:#0c0c0c;color:#e6edf3;font-family:system-ui,Segoe UI,sans-serif;display:flex;align-items:center;justify-content:center;padding:1.5rem;}
.card{max-width:420px;width:100%;background:#121212;border:1px solid #30363d;border-radius:6px;padding:1.25rem 1.35rem;}
h1{font-size:1rem;margin:0 0 0.75rem;font-weight:600;}
p{color:#8b949e;font-size:0.88rem;line-height:1.45;margin:0.5rem 0;}
label{display:block;margin:0.65rem 0 0.25rem;font-size:0.82rem;color:#8b949e;}
input{width:100%;box-sizing:border-box;padding:0.45rem 0.5rem;border-radius:4px;border:1px solid #30363d;background:#0d1117;color:#e6edf3;font:inherit;}
button,.btn{margin-top:0.85rem;padding:0.5rem 1rem;border-radius:4px;border:1px solid #30363d;background:#21262d;color:#58a6ff;font:inherit;cursor:pointer;font-weight:600;width:100%;}
button:hover,.btn:hover{background:#30363d;}
a{color:#58a6ff;}
.err{color:#f85149;font-size:0.85rem;margin-top:0.5rem;}
.ok{color:#3fb950;font-size:0.85rem;margin-top:0.5rem;}
</style></head><body><div class="card">${bodyHtml}</div></body></html>`;
}

function redirect(res, loc) {
  res.writeHead(302, { Location: loc, 'Cache-Control': 'no-store' });
  res.end();
}

function parseForm(body) {
  const p = new URLSearchParams(body);
  const o = {};
  for (const [k, v] of p) o[k] = v;
  return o;
}

/**
 * @param {import('http').IncomingMessage} req
 * @param {import('http').ServerResponse} res
 * @param {URL} url
 * @param {{ dbPath: () => string, readRequestBody: (req: import('http').IncomingMessage, limit?: number) => Promise<string> }} ctx
 * @returns {Promise<boolean>} true if request was handled
 */
export async function handleJupiterAuthHttp(req, res, url, ctx) {
  const p = url.pathname;
  const secret = getSessionSecret();
  if (!secret) {
    res.writeHead(503, { 'Content-Type': 'text/plain; charset=utf-8' });
    res.end('JUPITER_SESSION_SECRET is not set');
    return true;
  }

  const allowedEmail = getConfiguredAuthEmail();

  if (p === '/auth/login' && req.method === 'GET') {
    const next = url.searchParams.get('next') || '/dashboard';
    const body = authShell(
      'Sign in — Jupiter lab',
      `<h1>Sign in</h1>
      <p>Use the email and password for this lab. Forgot? Use the link below.</p>
      <form method="post" action="/auth/login">
        <input type="hidden" name="next" value="${htmlEscape(next)}"/>
        <label for="email">Email</label>
        <input id="email" name="email" type="email" autocomplete="username" value="${htmlEscape(allowedEmail)}" required/>
        <label for="password">Password</label>
        <input id="password" name="password" type="password" autocomplete="current-password" required/>
        <button type="submit">Sign in</button>
      </form>
      <p style="margin-top:1rem"><a href="/auth/forgot">Forgot password</a></p>`
    );
    res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store' });
    res.end(body);
    return true;
  }

  if (p === '/auth/login' && req.method === 'POST') {
    const raw = await ctx.readRequestBody(req);
    const f = parseForm(raw);
    const email = String(f.email || '').trim().toLowerCase();
    const password = String(f.password || '');
    const next = String(f.next || '/dashboard').startsWith('/') ? String(f.next || '/dashboard') : '/dashboard';
    let db;
    try {
      db = new DatabaseSync(ctx.dbPath());
      ensureJupiterWebAuthSchema(db);
      if (email !== allowedEmail || !verifyUserPassword(db, email, password)) {
        const body = authShell(
          'Sign in — Jupiter lab',
          `<h1>Sign in</h1><p class="err">Invalid email or password.</p>
          <form method="post" action="/auth/login"><input type="hidden" name="next" value="${htmlEscape(next)}"/>
          <label for="email">Email</label><input id="email" name="email" type="email" value="${htmlEscape(email)}" required/>
          <label for="password">Password</label><input id="password" name="password" type="password" required/>
          <button type="submit">Sign in</button></form>
          <p style="margin-top:1rem"><a href="/auth/forgot">Forgot password</a></p>`
        );
        res.writeHead(401, { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store' });
        res.end(body);
        return true;
      }
      setSessionCookie(res, email, secret);
      redirect(res, next);
      return true;
    } finally {
      try {
        db?.close();
      } catch {
        /* */
      }
    }
  }

  if ((p === '/auth/logout' && (req.method === 'GET' || req.method === 'POST')) || p === '/auth/logout/') {
    clearSessionCookie(res);
    redirect(res, '/auth/login');
    return true;
  }

  if (p === '/auth/forgot' && req.method === 'GET') {
    const body = authShell(
      'Forgot password — Jupiter lab',
      `<h1>Forgot password</h1>
      <p>If your email is registered, we will send a reset link (about one hour to use the link).</p>
      <form method="post" action="/auth/forgot">
        <label for="email">Email</label>
        <input id="email" name="email" type="email" value="${htmlEscape(allowedEmail)}" required/>
        <button type="submit">Send reset link</button>
      </form>
      <p style="margin-top:1rem"><a href="/auth/login">Back to sign in</a></p>`
    );
    res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store' });
    res.end(body);
    return true;
  }

  if (p === '/auth/forgot' && req.method === 'POST') {
    const raw = await ctx.readRequestBody(req);
    const f = parseForm(raw);
    const email = String(f.email || '').trim().toLowerCase();
    let db;
    try {
      db = new DatabaseSync(ctx.dbPath());
      ensureJupiterWebAuthSchema(db);
      await createResetAndEmail(db, email);
    } finally {
      try {
        db?.close();
      } catch {
        /* */
      }
    }
    const body = authShell(
      'Check email — Jupiter lab',
      `<h1>Check your email</h1>
      <p class="ok">If an account exists for that address, we sent a reset link. The link expires in about one hour.</p>
      <p>Forgot again? Repeat this page to get a new link.</p>
      <p><a href="/auth/login">Back to sign in</a></p>`
    );
    res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store' });
    res.end(body);
    return true;
  }

  if (p === '/auth/reset' && req.method === 'GET') {
    const token = url.searchParams.get('token') || '';
    if (!token) {
      const body = authShell('Reset password', `<h1>Invalid link</h1><p class="err">Missing token. Request a new link from <a href="/auth/forgot">Forgot password</a>.</p>`);
      res.writeHead(400, { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store' });
      res.end(body);
      return true;
    }
    let db;
    try {
      db = new DatabaseSync(ctx.dbPath());
      ensureJupiterWebAuthSchema(db);
      const em = peekResetToken(db, token);
      if (!em) {
        const body = authShell(
          'Reset link expired',
          `<h1>Link expired or already used</h1><p class="err">Request a new reset from <a href="/auth/forgot">Forgot password</a>.</p>`
        );
        res.writeHead(400, { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store' });
        res.end(body);
        return true;
      }
    } finally {
      try {
        db?.close();
      } catch {
        /* */
      }
    }
    const body = authShell(
      'Set new password',
      `<h1>Set a new password</h1>
      <form method="post" action="/auth/reset">
        <input type="hidden" name="token" value="${htmlEscape(token)}"/>
        <label for="p1">New password</label>
        <input id="p1" name="p1" type="password" autocomplete="new-password" required minlength="8"/>
        <label for="p2">Confirm</label>
        <input id="p2" name="p2" type="password" autocomplete="new-password" required minlength="8"/>
        <button type="submit">Save password</button>
      </form>`
    );
    res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store' });
    res.end(body);
    return true;
  }

  if (p === '/auth/reset' && req.method === 'POST') {
    const raw = await ctx.readRequestBody(req);
    const f = parseForm(raw);
    const token = String(f.token || '');
    const p1 = String(f.p1 || '');
    const p2 = String(f.p2 || '');
    if (p1 !== p2 || p1.length < 8) {
      const body = authShell(
        'Reset password',
        `<h1>Try again</h1><p class="err">Passwords must match and be at least 8 characters.</p>
        <form method="post" action="/auth/reset">
        <input type="hidden" name="token" value="${htmlEscape(token)}"/>
        <label for="p1">New password</label><input id="p1" name="p1" type="password" required minlength="8"/>
        <label for="p2">Confirm</label><input id="p2" name="p2" type="password" required minlength="8"/>
        <button type="submit">Save password</button></form>`
      );
      res.writeHead(400, { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store' });
      res.end(body);
      return true;
    }
    let db;
    try {
      db = new DatabaseSync(ctx.dbPath());
      ensureJupiterWebAuthSchema(db);
      const em = consumeResetToken(db, token);
      if (!em) {
        const body = authShell(
          'Reset failed',
          `<h1>Invalid or expired token</h1><p class="err"><a href="/auth/forgot">Request a new reset link</a>.</p>`
        );
        res.writeHead(400, { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store' });
        res.end(body);
        return true;
      }
      upsertUserPassword(db, em, p1);
      setSessionCookie(res, em, secret);
      redirect(res, '/dashboard');
      return true;
    } finally {
      try {
        db?.close();
      } catch {
        /* */
      }
    }
  }

  return false;
}

/**
 * @param {import('http').IncomingMessage} req
 * @param {import('http').ServerResponse} res
 * @param {URL} url
 * @param {{ wantsJson: boolean }} opts
 */
export function requireJupiterSession(req, res, url, opts) {
  const secret = getSessionSecret();
  const sess = getSessionFromRequest(req, secret);
  const allowed = getConfiguredAuthEmail();
  if (sess && sess.email === allowed) return true;

  if (opts.wantsJson) {
    res.writeHead(401, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' });
    res.end(JSON.stringify({ error: 'login_required', login: '/auth/login' }));
    return false;
  }
  const next = encodeURIComponent(url.pathname + url.search);
  redirect(res, `/auth/login?next=${next}`);
  return false;
}
