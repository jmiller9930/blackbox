/**
 * Trade-surface → Kitchen explicit runtime policy check-in (POST BlackBox
 * /api/v1/renaissance/runtime-policy-checkin). Kept separate from jupiter_web.mjs for tests.
 */

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
  if (!base || !token) {
    return { ok: false, skipped: true, reason: 'missing_base_or_token', httpStatus: 0, body: null };
  }
  if (!activePolicy) {
    return { ok: false, skipped: true, reason: 'missing_active_policy', httpStatus: 0, body: null };
  }
  const url = `${base}/api/v1/renaissance/runtime-policy-checkin`;
  const res = await fetchFn(url, {
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
  });
  let body = null;
  try {
    body = await res.json();
  } catch {
    body = null;
  }
  const ok = res.ok && body && body.ok === true;
  return { ok, httpStatus: res.status, body, skipped: false };
}

/**
 * @param {{
 *   beforePolicyId: string,
 *   afterPolicyId: string,
 *   env?: NodeJS.ProcessEnv,
 *   fetchImpl?: typeof fetch
 * }} opts
 */
export async function tradeSurfacePolicyKitchenHandshake(opts) {
  const env = opts.env || process.env;
  const base = String(env.JUPITER_KITCHEN_CHECKIN_BASE || '').trim();
  const token = String(env.JUPITER_KITCHEN_CHECKIN_TOKEN || '').trim();
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
    (r.body && (r.body.detail || r.body.error)) ||
    `Kitchen check-in failed (HTTP ${r.httpStatus || '?'})`;
  if (strict) {
    return {
      strictBlocked: true,
      kitchen_checkin: { ok: false, http_status: r.httpStatus, body: r.body },
      detail,
    };
  }
  return {
    strictBlocked: false,
    kitchen_checkin: { ok: false, http_status: r.httpStatus, body: r.body },
    kitchen_checkin_warning: `Kitchen did not acknowledge runtime policy change: ${String(detail).slice(0, 500)}`,
  };
}
