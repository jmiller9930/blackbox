# NDE: FinQuant

**NDE: FinQuant** is the first **Narrow Domain Expert** implemented under the **NDE Factory** umbrella — a narrow quant-finance verifier (FinQuant-1).

## Domain obligations → repository anchors

| Obligation | Where it lives today |
|------------|----------------------|
| Source manifest rules | `finquant/training/source_to_training.py` (concept manifests / hashing patterns described in dataset docs) |
| Dataset generation | `finquant/training/source_to_training.py`, staging outputs |
| Verifier contract | `finquant/docs/FinQuant-1_architecture.md` + verifier-shaped rows in staging |
| Eval cases | `finquant/evals/eval_finquant.py` |
| Training config defaults | `finquant/training/config_v0.1.yaml`, `train_qlora.py` |
| Promotion criteria | `finquant/reports/training_control_plane_v0.1.md` (design); operational gates TBD per rollout |

## Related docs

- Architecture (narrow verifier story): `finquant/docs/FinQuant-1_architecture.md`
- Factory terminology: `finquant/reports/nde_factory_v0.1.md`
- Control plane M1: `finquant/reports/control_plane_m1_report.md`

This README does **not** duplicate implementation; it maps **NDE Factory domain obligations** to current paths until code is reorganized under an explicit factory package.
