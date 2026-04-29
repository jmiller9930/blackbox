# NDE Factory — domain modules

This directory holds **Narrow Domain Expert (NDE)** domain definitions for the **NDE Factory** (reusable training, eval, and control-plane patterns).

- **Factory framing:** `finquant/reports/nde_factory_v0.1.md`
- **First domain:** **NDE: FinQuant** — see `finquant/README.md` and `domains/finquant/README.md`

## Layout

| Path | Purpose |
|------|---------|
| `domains/finquant/` | **NDE: FinQuant** — pointers and future colocated domain contract |
| `domains/vmware/` | **Example stub** for a future domain (no product commitment) |

Add new domains as **`domains/<name>/`** with a README that covers: source manifest rules, dataset generation, verifier contract, eval cases, training defaults, promotion criteria.

**Note:** Training and dataset **code** for FinQuant still live under `finquant/` in the tree today; this folder is the **abstraction boundary** for documentation and phased migration — see `nde_factory_v0.1.md` §11.

**Training-server data tree (`/data/NDE/`):** Canonical files live under **`nde_factory/layout/`**; install with **`scripts/install_nde_data_layout.sh`** on the host (does not modify `/data/finquant-1/`).
