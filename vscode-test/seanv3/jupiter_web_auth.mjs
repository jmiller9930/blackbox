/**
 * Session login + email password reset for jupiter-web (optional; lab).
 * Login id: JUPITER_AUTH_USERNAME (default admin). Reset links go to JUPITER_AUTH_EMAIL.
 * Secrets: JUPITER_SESSION_SECRET, optional RESEND_API_KEY for outbound mail.
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
      username TEXT PRIMARY KEY COLLATE NOCASE,
      password_scrypt BLOB NOT NULL,
      salt BLOB NOT NULL,
      updated_utc TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS ${RESET_TABLE} (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      token_hash TEXT NOT NULL UNIQUE,
      username TEXT NOT NULL COLLATE NOCASE,
      expires_utc TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_jw_reset_exp ON ${RESET_TABLE} (expires_utc);
  `);
  migrateAuthSchemaEmailToUsername(db);
}

function migrateAuthSchemaEmailToUsername(db) {
  try {
    const cols = db.prepare(`PRAGMA table_info(${USER_TABLE})`).all();
    const names = cols.map((/** @type {{ name: string }} */ c) => c.name);
    if (names.includes('email') && !names.includes('username')) {
      db.exec(`ALTER TABLE ${USER_TABLE} RENAME COLUMN email TO username`);
    }
  } catch (e) {
    console.error('[jupiter-auth] user table migrate:', e instanceof Error ? e.message : e);
  }
  try {
    const cols = db.prepare(`PRAGMA table_info(${RESET_TABLE})`).all();
    const names = cols.map((/** @type {{ name: string }} */ c) => c.name);
    if (names.includes('email') && !names.includes('username')) {
      db.exec(`ALTER TABLE ${RESET_TABLE} RENAME COLUMN email TO username`);
    }
  } catch (e) {
    console.error('[jupiter-auth] reset table migrate:', e instanceof Error ? e.message : e);
  }
  const em = getConfiguredAuthEmail();
  const un = getConfiguredUsername();
  if (em.includes('@') && un) {
    const row = db.prepare(`SELECT password_scrypt, salt, updated_utc FROM ${USER_TABLE} WHERE username = ?`).get(em);
    if (row) {
      db.prepare(`DELETE FROM ${USER_TABLE} WHERE username = ?`).run(em);
      db.prepare(
        `INSERT INTO ${USER_TABLE} (username, password_scrypt, salt, updated_utc) VALUES (?, ?, ?, ?)`
      ).run(un, row.password_scrypt, row.salt, row.updated_utc);
      console.error(`[jupiter-auth] migrated login id from ${em} to username ${un}`);
    }
  }
}

export function getConfiguredAuthEmail() {
  return (process.env.JUPITER_AUTH_EMAIL || 'jmiller9930@om3.us').trim().toLowerCase();
}

export function getConfiguredUsername() {
  return (process.env.JUPITER_AUTH_USERNAME || 'admin').trim().toLowerCase();
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

function signSessionPayload(user, expSec, secret) {
  const payload = `${expSec}|${user}`;
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
  const user = payload.slice(first + 1);
  if (!Number.isFinite(expSec) || expSec < Math.floor(Date.now() / 1000)) return null;
  return { user: user.toLowerCase(), expSec };
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
 * @param {string} username
 * @param {string} password
 */
export function upsertUserPassword(db, username, password) {
  const salt = randomBytes(16);
  const pw = hashPassword(password, salt);
  const u = String(username).trim().toLowerCase();
  db.prepare(
    `INSERT INTO ${USER_TABLE} (username, password_scrypt, salt, updated_utc)
     VALUES (?, ?, ?, ?)
     ON CONFLICT(username) DO UPDATE SET
       password_scrypt = excluded.password_scrypt,
       salt = excluded.salt,
       updated_utc = excluded.updated_utc`
  ).run(u, pw, salt, new Date().toISOString());
}

/**
 * @param {import('node:sqlite').DatabaseSync} db
 * @param {string} username
 * @param {string} password
 */
export function verifyUserPassword(db, username, password) {
  const u = String(username).trim().toLowerCase();
  const row = db.prepare(`SELECT password_scrypt, salt FROM ${USER_TABLE} WHERE username = ?`).get(u);
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
  const username = getConfiguredUsername();
  const bootstrap =
    (
      process.env.JUPITER_AUTH_BOOTSTRAP_PASSWORD ||
      process.env.JUPITER_WEB_LOGIN_PASSWORD ||
      ''
    ).trim();
  if (!username || !bootstrap) return;
  const n = db.prepare(`SELECT COUNT(*) AS c FROM ${USER_TABLE}`).get();
  const count = n && typeof n.c === 'number' ? n.c : 0;
  if (count > 0) return;
  upsertUserPassword(db, username, bootstrap);
  console.error(
    `[jupiter-auth] bootstrapped login for username ${username} from env — remove JUPITER_AUTH_BOOTSTRAP_PASSWORD / JUPITER_WEB_LOGIN_PASSWORD from the container`
  );
}

/** @param {import('http').ServerResponse} res */
export function setSessionCookie(res, username, secret) {
  const maxAgeSec = Math.max(60, Math.min(60 * 60 * 24 * 30, parseInt(process.env.JUPITER_SESSION_MAX_AGE_SEC || '604800', 10) || 604800));
  const expSec = Math.floor(Date.now() / 1000) + maxAgeSec;
  const val = signSessionPayload(username.toLowerCase(), expSec, secret);
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
 */
export async function createResetAndEmail(db) {
  const un = getConfiguredUsername();
  const row = db.prepare(`SELECT username FROM ${USER_TABLE} WHERE username = ?`).get(un);
  if (!row) return { ok: true, generic: true };
  const mailTo = getConfiguredAuthEmail();
  const token = randomBytes(32).toString('hex');
  const th = hashToken(token);
  const exp = new Date(Date.now() + 60 * 60 * 1000).toISOString();
  db.prepare(`DELETE FROM ${RESET_TABLE} WHERE username = ?`).run(un);
  db.prepare(`INSERT INTO ${RESET_TABLE} (token_hash, username, expires_utc) VALUES (?, ?, ?)`).run(th, un, exp);
  const base = getPublicBaseUrl();
  const url = buildResetUrl(base, token);
  await sendPasswordResetEmail(mailTo, url);
  return { ok: true, generic: true };
}

/** Read-only: token valid and not expired (does not delete). */
export function peekResetToken(db, token) {
  const th = hashToken(token);
  const row = db.prepare(`SELECT username, expires_utc FROM ${RESET_TABLE} WHERE token_hash = ?`).get(th);
  if (!row) return null;
  const exp = new Date(String(row.expires_utc)).getTime();
  if (!Number.isFinite(exp) || Date.now() > exp) {
    db.prepare(`DELETE FROM ${RESET_TABLE} WHERE token_hash = ?`).run(th);
    return null;
  }
  return String(row.username).toLowerCase();
}

/** Verify and delete token row (use on POST after password change). */
export function consumeResetToken(db, token) {
  const th = hashToken(token);
  const row = db.prepare(`SELECT username, expires_utc FROM ${RESET_TABLE} WHERE token_hash = ?`).get(th);
  if (!row) return null;
  const exp = new Date(String(row.expires_utc)).getTime();
  if (!Number.isFinite(exp) || Date.now() > exp) {
    db.prepare(`DELETE FROM ${RESET_TABLE} WHERE token_hash = ?`).run(th);
    return null;
  }
  db.prepare(`DELETE FROM ${RESET_TABLE} WHERE token_hash = ?`).run(th);
  return String(row.username).toLowerCase();
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
/* Full-bleed lab artwork at full visibility (not the 15% dashboard tint). */
html,body{height:100%;}
body{
  margin:0;min-height:100vh;color:#e6edf3;font-family:system-ui,Segoe UI,sans-serif;
  display:flex;align-items:center;justify-content:center;padding:1.25rem;
  background:#050508 url(/static/jupiter_front_door.png) center center / cover no-repeat;
  background-color:#050508;
}
/* Light scrim so type stays readable; art still reads clearly. */
body::after{
  content:'';position:fixed;inset:0;background:linear-gradient(160deg,rgba(5,5,8,0.35),rgba(5,5,8,0.55));pointer-events:none;z-index:0;
}
.card{
  position:relative;z-index:1;max-width:420px;width:100%;
  background:rgba(12,12,14,0.72);border:1px solid rgba(255,255,255,0.12);border-radius:10px;padding:1.35rem 1.4rem;
  box-shadow:0 12px 40px rgba(0,0,0,0.45);backdrop-filter:blur(10px);
}
h1{font-size:1.05rem;margin:0 0 0.65rem;font-weight:600;text-shadow:0 1px 2px rgba(0,0,0,0.6);}
p{color:#c9d1d9;font-size:0.88rem;line-height:1.45;margin:0.5rem 0;text-shadow:0 1px 2px rgba(0,0,0,0.5);}
label{display:block;margin:0.75rem 0 0.3rem;font-size:0.78rem;font-weight:600;text-transform:uppercase;letter-spacing:0.04em;color:#e6edf3;}
/* Knockouts: type through “holes” so the artwork shows inside the field. */
input.jw-knockout{
  width:100%;box-sizing:border-box;padding:0.55rem 0.65rem;border-radius:6px;font:inherit;font-size:0.95rem;color:#f0f6fc;
  border:2px solid rgba(255,255,255,0.45);
  background:rgba(0,0,0,0.18);
  backdrop-filter:blur(8px) saturate(1.1);
  box-shadow:inset 0 0 0 1px rgba(0,0,0,0.25);
}
input.jw-knockout::placeholder{color:rgba(230,237,243,0.45);}
input.jw-knockout:focus{
  outline:none;border-color:rgba(88,166,255,0.85);
  background:rgba(0,0,0,0.28);
  box-shadow:0 0 0 3px rgba(88,166,255,0.2),inset 0 0 0 1px rgba(0,0,0,0.3);
}
button,.btn{
  margin-top:1rem;padding:0.55rem 1rem;border-radius:6px;border:1px solid rgba(88,166,255,0.45);
  background:rgba(33,38,45,0.92);color:#58a6ff;font:inherit;cursor:pointer;font-weight:600;width:100%;
  backdrop-filter:blur(6px);
}
button:hover,.btn:hover{background:rgba(48,54,61,0.95);border-color:rgba(88,166,255,0.75);}
a{color:#79c0ff;}
.err{color:#ffb1a8;font-size:0.85rem;margin-top:0.5rem;}
.ok{color:#aff5c4;font-size:0.85rem;margin-top:0.5rem;}
code{font-size:0.8rem;background:rgba(0,0,0,0.35);padding:0.1rem 0.35rem;border-radius:4px;}
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

  const allowedUser = getConfiguredUsername();

  if (p === '/auth/login' && req.method === 'GET') {
    const next = url.searchParams.get('next') || '/dashboard';
    const body = authShell(
      'Sign in — Jupiter lab',
      `<h1>Sign in</h1>
      <p>Username and password for this lab. Forgot password? We email a reset link to your registered address.</p>
      <form method="post" action="/auth/login">
        <input type="hidden" name="next" value="${htmlEscape(next)}"/>
        <label for="username">Username</label>
        <input class="jw-knockout" id="username" name="username" type="text" autocomplete="username" value="${htmlEscape(allowedUser)}" required autocapitalize="off"/>
        <label for="password">Password</label>
        <input class="jw-knockout" id="password" name="password" type="password" autocomplete="current-password" required/>
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
    const username = String(f.username || '').trim().toLowerCase();
    const password = String(f.password || '');
    const next = String(f.next || '/dashboard').startsWith('/') ? String(f.next || '/dashboard') : '/dashboard';
    let db;
    try {
      db = new DatabaseSync(ctx.dbPath());
      ensureJupiterWebAuthSchema(db);
      if (username !== allowedUser || !verifyUserPassword(db, username, password)) {
        const body = authShell(
          'Sign in — Jupiter lab',
          `<h1>Sign in</h1><p class="err">Invalid username or password.</p>
          <form method="post" action="/auth/login"><input type="hidden" name="next" value="${htmlEscape(next)}"/>
          <label for="username">Username</label><input class="jw-knockout" id="username" name="username" type="text" value="${htmlEscape(username)}" required autocapitalize="off"/>
          <label for="password">Password</label><input class="jw-knockout" id="password" name="password" type="password" required/>
          <button type="submit">Sign in</button></form>
          <p style="margin-top:1rem"><a href="/auth/forgot">Forgot password</a></p>`
        );
        res.writeHead(401, { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store' });
        res.end(body);
        return true;
      }
      setSessionCookie(res, username, secret);
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
    const mail = getConfiguredAuthEmail();
    const body = authShell(
      'Forgot password — Jupiter lab',
      `<h1>Forgot password</h1>
      <p>We will send a one-time reset link to <strong>${htmlEscape(mail)}</strong> (about one hour to use it). If Resend is not configured, check <code>docker logs jupiter-web</code> for the link.</p>
      <form method="post" action="/auth/forgot">
        <button type="submit">Email me a reset link</button>
      </form>
      <p style="margin-top:1rem"><a href="/auth/login">Back to sign in</a></p>`
    );
    res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store' });
    res.end(body);
    return true;
  }

  if (p === '/auth/forgot' && req.method === 'POST') {
    let db;
    try {
      db = new DatabaseSync(ctx.dbPath());
      ensureJupiterWebAuthSchema(db);
      await createResetAndEmail(db);
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
      <p class="ok">If this lab account exists, we sent a reset link to your registered address. The link expires in about one hour.</p>
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
        <input class="jw-knockout" id="p1" name="p1" type="password" autocomplete="new-password" required minlength="8"/>
        <label for="p2">Confirm</label>
        <input class="jw-knockout" id="p2" name="p2" type="password" autocomplete="new-password" required minlength="8"/>
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
        <label for="p1">New password</label><input class="jw-knockout" id="p1" name="p1" type="password" required minlength="8"/>
        <label for="p2">Confirm</label><input class="jw-knockout" id="p2" name="p2" type="password" required minlength="8"/>
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
  const allowed = getConfiguredUsername();
  if (sess && sess.user === allowed) return true;

  if (opts.wantsJson) {
    res.writeHead(401, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' });
    res.end(JSON.stringify({ error: 'login_required', login: '/auth/login' }));
    return false;
  }
  const next = encodeURIComponent(url.pathname + url.search);
  redirect(res, `/auth/login?next=${next}`);
  return false;
}
