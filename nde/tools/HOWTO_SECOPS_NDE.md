# SecOps NDE — HOWTO

## Prerequisites

1. Install layout from the repo: `bash scripts/install_nde_data_layout.sh /data/NDE`
2. Domain contract (paths must exist before the graph runs):

   * `/data/NDE/secops/domain_config.yaml`
   * `/data/NDE/secops/training/config.yaml`
   * `/data/NDE/secops/eval/eval_v1.json`
   * `/data/NDE/secops/eval/final_exam_v1.json`
   * `/data/NDE/secops/datasets/staging/` (staging JSONL per `training/config.yaml`)

3. Optional checks:

```bash
/data/NDE/tools/validate_domain_contract.py --nde-root /data/NDE --domain secops
/data/NDE/tools/validate_training_dataset.py --nde-root /data/NDE --domain secops
```

## Kick off (smoke)

Run on the NDE host:

```bash
/data/NDE/tools/run_graph.sh --domain secops --mode smoke
```

## What the system does (LangGraph)

* validate_domain_contract
* validate_training_dataset
* smoke_train
* smoke_eval
* evaluate_gate
* auto_reinforce (if eval gate fails)
* retry_or_escalate (re-check dataset / retry policy)
* final_exam (when gate passes)
* certify (when final exam passes)

## Where to look

Run folder:

```
/data/NDE/secops/runs/<run_id>/
```

Key files:

* `state.json` — overall status
* `nodes/<node>/node_status.json` — per-step proof (inputs/outputs/errors/next_node)
* `CERTIFICATE.json` — only present if fully certified (includes model, dataset hash, eval/final scores)

## Full training (only after approval)

```bash
touch /data/NDE/secops/runs/<run_id>/APPROVED

/data/NDE/tools/run_graph.sh \
  --domain secops \
  --mode full \
  --require-approval
```

## Rules

* Do not run training or eval outside LangGraph for NDE certification flows
* Do not bypass LangGraph
* Staging JSONL must satisfy `validate_training_dataset.py` before certification is meaningful
* Certification requires final exam pass
