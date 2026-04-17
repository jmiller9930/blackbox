/**
 * Trade-surface → Kitchen explicit runtime policy check-in (POST BlackBox
 * /api/v1/renaissance/runtime-policy-checkin). Kept separate from jupiter_web.mjs for tests.
 *
 * Notes on the hardening in this file:
 * - The first handshake version assumed `fetch()` would always settle into an HTTP response.
 * - In practice, the dangerous failures here are the transport failures: DNS issues, refused
 *   connections, stalled sockets, or upstream timeouts.
 * - If one of those exceptions bubbles out after Jupiter has already written the local policy,
 *   the caller can miss the strict-mode rollback path and we end up with exactly the split-brain
 *   condition this handshake was meant to prevent.
 * - The helpers below therefore convert transport failures and timeout/abort events into a normal
 *   structured "check-in failed" result so the caller can decide whether to warn (relaxed mode)
 *   or roll back the runtime write (strict mode).
 */

const DEFAULT_KITCHEN_CHECKIN_TIMEOUT_MS = 8000;

function parseKitchenCheckinTimeoutMs(rawValue) {
  const n = Number.parseInt(String(rawValue || '').trim(), 10);
  if (!Number.isFinite(n) || n <= 0) {
    return DEFAULT_KITCHEN_CHECKIN_TIMEOUT_MS;
  }
  return Math.max(1000, Math.min(60000, n));
}

/**
 * @param {{
 *   baseUrl: string,
 *   token: string,
 *   executionTarget?: string,
 *   activePolicy: string,
 *   changeSource?: string,
 *   fetchImpl?: typeof fetch
 * }} opts
 */
export async function kitchenRuntimePolicyCheckinHttp(opts) {
  const base = String(opts.baseUrl || '')
    .trim()
    .replace(/\/$/, '');
  const token = String(opts.token || '').trim();
  const executionTarget = String(opts.executionTarget || 'jupiter').trim();
  const activePolicy = String(opts.activePolicy || '').trim();
  const changeSource = String(opts.changeSource || 'trade_surface_manual').trim();
  const fetchFn = opts.fetchImpl || globalThis.fetch;
  const timeoutMs = parseKitchenCheckinTimeoutMs(opts.timeoutMs);
  if (!base || !token) {
    return { ok: false, skipped: true, reason: 'missing_base_or_token', httpStatus: 0, body: null };
  }
  // Empty activePolicy is valid: explicit standby / unassign (POST active_policy "").
  if (typeof fetchFn !== 'function') {
    return {
      ok: false,
      skipped: false,
      reason: 'fetch_not_available',
      httpStatus: 0,
      body: null,
      detail: 'No fetch implementation is available for Kitchen runtime check-in.',
    };
  }
  const url = `${base}/api/v1/renaissance/runtime-policy-checkin`;
  const supportsAbort = typeof AbortController === 'function';
  const controller = supportsAbort ? new AbortController() : null;
  const timer =
    controller !== null
      ? setTimeout(() => controller.abort(new Error(`Kitchen check-in timed out after ${timeoutMs}ms`)), timeoutMs)
      : null;
  let res;
  try {
    res = await fetchFn(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({
        execution_target: executionTarget,
        active_policy: activePolicy,
        change_source: changeSource,
      }),
      signal: controller ? controller.signal : undefined,
    });
  } catch (err) {
    if (timer) {
      clearTimeout(timer);
    }
    const detail = err instanceof Error ? err.message : String(err);
    const reason =
      err instanceof Error && err.name === 'AbortError' ? 'request_timeout' : 'request_exception';
    return {
      ok: false,
      skipped: false,
      reason,
      httpStatus: 0,
      body: null,
      detail: String(detail || 'Kitchen check-in request failed unexpectedly.').slice(0, 500),
    };
  }
  let body = null;
  try {
    body = await res.json();
  } catch {
    body = null;
  }
  if (timer) {
    clearTimeout(timer);
  }
  const ok = res.ok && body && body.ok === true;
  return { ok, httpStatus: res.status, body, skipped: false };
}

/**
 * @param {{
 *   beforePolicyId: string,
 *   afterPolicyId: string,
 *   env?: NodeJS.ProcessEnv,
 *   fetchImpl?: typeof fetch,
 *   timeoutMs?: number
 * }} opts
 */
export async function tradeSurfacePolicyKitchenHandshake(opts) {
  const env = opts.env || process.env;
  const base = String(env.JUPITER_KITCHEN_CHECKIN_BASE || '').trim();
  const token = String(env.JUPITER_KITCHEN_CHECKIN_TOKEN || '').trim();
  const timeoutMs = parseKitchenCheckinTimeoutMs(opts.timeoutMs || env.JUPITER_KITCHEN_CHECKIN_TIMEOUT_MS);
  const strict = ['1', 'true', 'yes'].includes(
    String(env.JUPITER_REQUIRE_KITCHEN_ACK || '')
      .trim()
      .toLowerCase()
  );
  if (!base || !token) {
    if (strict) {
      return {
        strictBlocked: true,
        kitchen_checkin: { ok: false, skipped: true, reason: 'env_not_configured' },
        detail: 'JUPITER_REQUIRE_KITCHEN_ACK is set but Kitchen check-in URL/token are not configured.',
      };
    }
    return {
      strictBlocked: false,
      kitchen_checkin: {
        ok: false,
        skipped: true,
        reason: 'env_not_configured',
        message: 'Kitchen check-in skipped (set JUPITER_KITCHEN_CHECKIN_BASE and JUPITER_KITCHEN_CHECKIN_TOKEN to acknowledge).',
      },
    };
  }
  const r = await kitchenRuntimePolicyCheckinHttp({
    baseUrl: base,
    token,
    executionTarget: 'jupiter',
    activePolicy: opts.afterPolicyId,
    changeSource: 'trade_surface_manual',
    fetchImpl: opts.fetchImpl,
    timeoutMs,
  });
  if (r.ok) {
    return {
      strictBlocked: false,
      kitchen_checkin: {
        ok: true,
        reconcile_linkage: r.body && r.body.reconcile_linkage,
        schema: r.body && r.body.schema,
      },
    };
  }
  const detail =
    r.detail ||
    (r.body && (r.body.detail || r.body.error)) ||
    `Kitchen check-in failed (HTTP ${r.httpStatus || '?'})`;
  if (strict) {
    return {
      strictBlocked: true,
      kitchen_checkin: { ok: false, http_status: r.httpStatus, body: r.body, detail },
      detail,
    };
  }
  return {
    strictBlocked: false,
    kitchen_checkin: { ok: false, http_status: r.httpStatus, body: r.body, detail },
    kitchen_checkin_warning: `Kitchen did not acknowledge runtime policy change: ${String(detail).slice(0, 500)}`,
  };
}
