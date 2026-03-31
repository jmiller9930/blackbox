/**
 * BLACK BOX portal — shared session, dev bootstrap auth, and API/event layer (Phase 4).
 * Production auth replaces DEV_ACCOUNTS via engine `/api/v1/` when wired.
 */
(function () {
  "use strict";

  var SESSION_KEY = "blackbox_portal_session_v1";

  /** @type {Record<string, { password: string, role: string, user_id: string }>} */
  var DEV_ACCOUNTS = {
    admin: {
      password: "admin",
      role: "internal_admin",
      user_id: "dev-bootstrap-admin",
    },
    consumer: {
      password: "consumer",
      role: "consumer_user",
      user_id: "dev-bootstrap-consumer",
    },
  };

  function readApiBase() {
    var el = document.querySelector('meta[name="blackbox-api-base"]');
    return el && el.content ? String(el.content).trim().replace(/\/+$/, "") : "";
  }

  function getSession() {
    try {
      var raw = sessionStorage.getItem(SESSION_KEY);
      if (!raw) return null;
      var o = JSON.parse(raw);
      if (!o || typeof o !== "object") return null;
      if (!o.role || !o.username) return null;
      return o;
    } catch (e) {
      return null;
    }
  }

  function setSession(payload) {
    sessionStorage.setItem(SESSION_KEY, JSON.stringify(payload));
  }

  function clearSession() {
    sessionStorage.removeItem(SESSION_KEY);
  }

  /**
   * Dev bootstrap only. Engine must verify credentials and issue session/token later.
   * @returns {{ ok: true, session: object } | { ok: false, error: string }}
   */
  function login(username, password) {
    var u = String(username || "").trim();
    var p = String(password || "");
    var rec = DEV_ACCOUNTS[u];
    if (!rec || rec.password !== p) {
      return { ok: false, error: "Invalid username or password." };
    }
    var session = {
      username: u,
      role: rec.role,
      user_id: rec.user_id,
      issued_at: new Date().toISOString(),
    };
    setSession(session);
    return { ok: true, session: session };
  }

  function portalPathForRole(role) {
    if (role === "internal_admin") return "internal.html";
    if (role === "consumer_user") return "consumer.html";
    return "login.html";
  }

  /**
   * @param {{ requiredRole: string, loginHref?: string }} opts
   */
  function protectPage(opts) {
    var loginHref = opts.loginHref || "login.html";
    var s = getSession();
    if (!s) {
      window.location.href = loginHref;
      return false;
    }
    if (s.role !== opts.requiredRole) {
      window.location.href = portalPathForRole(s.role);
      return false;
    }
    return true;
  }

  /**
   * Any logged-in user (internal_admin or consumer_user).
   * @param {{ loginHref?: string }} [opts]
   */
  function protectAuthenticated(opts) {
    var loginHref = (opts && opts.loginHref) || "login.html";
    var s = getSession();
    if (!s) {
      window.location.href = loginHref;
      return false;
    }
    if (s.role !== "internal_admin" && s.role !== "consumer_user") {
      window.location.href = loginHref;
      return false;
    }
    return true;
  }

  /**
   * Engine `/api/v1/` paths for self-service and admin (implement on server).
   * Client sends JSON; server enforces hashing, tokens, rate limits, audit.
   */
  var ACCOUNT_API = {
    register: "/auth/register",
    passwordResetRequest: "/auth/password-reset/request",
    passwordResetComplete: "/auth/password-reset/complete",
    emailVerify: "/auth/email/verify",
    emailResend: "/auth/email/resend-verification",
    accountMe: "/account/me",
    accountPassword: "/account/password",
    adminUsers: "/admin/users",
    adminInvite: "/admin/users/invite",
  };

  function accountApiClient() {
    var api = createApiClient();
    return {
      paths: ACCOUNT_API,
      register: function (body) {
        return api.post(ACCOUNT_API.register, body);
      },
      requestPasswordReset: function (email) {
        return api.post(ACCOUNT_API.passwordResetRequest, { email: email });
      },
      completePasswordReset: function (token, newPassword) {
        return api.post(ACCOUNT_API.passwordResetComplete, {
          token: token,
          new_password: newPassword,
        });
      },
      verifyEmail: function (token) {
        return api.post(ACCOUNT_API.emailVerify, { token: token });
      },
      resendVerification: function () {
        return api.post(ACCOUNT_API.emailResend, {});
      },
      getProfile: function () {
        return api.get(ACCOUNT_API.accountMe);
      },
      changePassword: function (currentPassword, newPassword) {
        return api.post(ACCOUNT_API.accountPassword, {
          current_password: currentPassword,
          new_password: newPassword,
        });
      },
      listUsers: function () {
        return api.get(ACCOUNT_API.adminUsers);
      },
      inviteUser: function (body) {
        return api.post(ACCOUNT_API.adminInvite, body);
      },
    };
  }

  function normalizePath(path) {
    var p = path.startsWith("/") ? path : "/" + path;
    return p;
  }

  function apiError(message, cause) {
    var e = new Error(message);
    e.cause = cause;
    e.blackboxApi = true;
    return e;
  }

  function createApiClient() {
    var eventSource = null;

    async function request(method, path, body) {
      var base = readApiBase();
      if (!base) {
        throw apiError(
          "API base URL is not configured (set meta blackbox-api-base)."
        );
      }
      var url = base + "/api/v1" + normalizePath(path);
      var headers = { Accept: "application/json" };
      if (body !== undefined) headers["Content-Type"] = "application/json";
      var s = getSession();
      if (s && s.token) headers["Authorization"] = "Bearer " + s.token;

      var res;
      try {
        res = await fetch(url, {
          method: method,
          headers: headers,
          body: body !== undefined ? JSON.stringify(body) : undefined,
          credentials: "include",
        });
      } catch (err) {
        throw apiError("Network error calling the engine API.", err);
      }

      var text = await res.text();
      var data = null;
      if (text) {
        try {
          data = JSON.parse(text);
        } catch (parseErr) {
          data = { raw: text };
        }
      }

      if (!res.ok) {
        var msg =
          (data && (data.message || data.error || data.reason_code)) ||
          "Request failed (" + res.status + ").";
        var err = apiError(msg);
        err.status = res.status;
        err.body = data;
        throw err;
      }

      return data;
    }

    return {
      get: function (path) {
        return request("GET", path, undefined);
      },
      post: function (path, body) {
        return request("POST", path, body);
      },
      /**
       * Opens SSE when API base is set; otherwise returns null (caller must handle).
       * @param {string} streamPath e.g. "/stream/status"
       * @param {(ev: MessageEvent) => void} onMessage
       * @param {(err: Event) => void} [onError]
       * @returns {EventSource | null}
       */
      connectEventSource: function (streamPath, onMessage, onError) {
        var base = readApiBase();
        if (!base) return null;
        var url = base + "/api/v1" + normalizePath(streamPath);
        if (eventSource) {
          try {
            eventSource.close();
          } catch (c) {}
          eventSource = null;
        }
        eventSource = new EventSource(url, { withCredentials: true });
        eventSource.onmessage = onMessage;
        eventSource.onerror =
          onError ||
          function () {
            /* fail closed: surface in UI panels when wired */
          };
        return eventSource;
      },
      closeEventSource: function () {
        if (eventSource) {
          try {
            eventSource.close();
          } catch (c) {}
          eventSource = null;
        }
      },
    };
  }

  window.BlackboxPortal = {
    SESSION_KEY: SESSION_KEY,
    readApiBase: readApiBase,
    getSession: getSession,
    setSession: setSession,
    clearSession: clearSession,
    login: login,
    portalPathForRole: portalPathForRole,
    protectPage: protectPage,
    protectAuthenticated: protectAuthenticated,
    ACCOUNT_API: ACCOUNT_API,
    account: accountApiClient(),
    api: createApiClient(),
  };
})();
