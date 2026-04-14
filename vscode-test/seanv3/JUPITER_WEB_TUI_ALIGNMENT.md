# Jupiter web vs SeanV3 TUI — operator alignment

## What you mean (and what we agree on)

- **Backend** = SeanV3 runtime: poll/engine, policy execution, `capture/sean_parity.db`, and everything that **writes** operator-relevant state.
- **TUI** = one **display surface**: terminal UI (`preflight_pyth_tui.py`) that **reads** that state and shows it in Rich panels.
- **Web (Jupiter)** = another **display surface**: browser UI (`jupiter_web.mjs`) that should **read the same state** and present it — a **window** onto the backend, not a second source of truth.

So: **same facts, two renderers.** The web is not “less true”; it is **incomplete today** if it omits facts the TUI shows.

## Fair expectation (product)

**Yes, it is fair** to expect that when you open the browser to Jupiter, you see **the same information** the TUI would show for the same moment and same DB — **subject only to**:

- **Refresh:** TUI can update live; the web may need explicit refresh or later auto-refresh unless we add it.
- **Things the TUI computes from non-DB sources** (e.g. preflight HTTP checks, BlackBox ledger paths): those must be **either** replicated in the web (call same helpers / show same files) **or** listed as **explicit exclusions** with a one-line reason.
- **Layout:** Parity is **information parity** first; pixel-perfect Rich layout is optional.

## Current gap (honest)

The web today implements a **subset** of what the TUI shows (wallet/position/kline/recent trades from SQLite). The TUI adds panels and context (preflight, parity vs BlackBox, ledger detail, trading mode, policy, clock, etc.). Until the web surfaces **every operator-relevant field the TUI surfaces** (or we agree a written exclusion list), **“open browser = same as TUI”** is an aspiration, not a guarantee.

## What needs to happen to be aligned (no code — checklist)

1. **Inventory** — Enumerate every TUI panel and data source (DB tables, files, env, live HTTP checks). Mark each as: **must appear on web**, **defer**, or **exclude**.
2. **Single source of truth** — For each “must appear” item, confirm it comes from the same place the TUI uses (usually `sean_parity.db` + documented paths).
3. **Web information parity** — Extend Jupiter web until **must appear** items are shown (tables, banners, links, JSON export as needed).
4. **Refresh policy** — Decide: manual refresh only vs periodic/auto refresh vs “good enough for v1”.
5. **Operator proof** — Side-by-side: same host, same time, TUI vs browser — checklist sign-off.

## Do we need a screenshot of the TUI?

**Helpful but not mandatory.** The TUI is defined in code (`scripts/operator/preflight_pyth_tui.py`); we can derive the inventory from there. A **screenshot** (or short screen recording) still helps for **priority** (“this panel matters most”) and **layout cues** if we want the web to **feel** closer to the TUI.

---

*This file is the alignment contract for “web = display window on the same backend as the TUI.” Update it when scope changes.*
