# GT_DIRECTIVE_016 — operator proof: L1 road (`GET /api/student-panel/l1-road`)

**Purpose:** Show **brain-profile–split** aggregates on one **fingerprint** ruler, **A \| B** vs baseline anchor, **Qwen vs DeepSeek** as separate LLM groups, and **API-delivered legend** (no UI-only semantics).

## Fixture input (committed)

Scorecard-shaped lines (same keys as `batch_scorecard.jsonl` rows):  
`renaissance_v4/game_theory/tests/fixtures/gt_directive_016_l1_road_scorecard_lines.json`

- Fingerprint **`aaaaaaaa…`**: baseline → memory → Qwen LLM → DeepSeek LLM (chronological).  
- Fingerprint **`bbbbbbbb…`**: memory-only row (no baseline in chain → `band: data_gap` + gap code).

## Aggregated response (committed)

Full JSON body from `build_l1_road_payload_v1(lines=<fixture>)` (matches HTTP payload shape):  
`renaissance_v4/game_theory/docs/proof/exam_v1/GT_DIRECTIVE_016_operator_proof_l1_road_response_v1.json`

**Spot checks:**

- Five **groups** (baseline ruler + memory + two LLM models on fp `aaaaaaaa…` + memory on fp `bbbbbbbb…`).  
- **Qwen** group: `band` **B** (E and P below anchor). **DeepSeek** group: `band` **A**. **Memory** on fp A: `band` **A**.  
- **Legend** block includes `brain_profiles`, `band_a`, `band_b`, `pass_rate_percent`, `avg_e_expectancy_per_trade`, `avg_p_process_score`.

## HTTP (live server)

```bash
curl -s -o /dev/null -w "%{http_code}\n" "http://127.0.0.1:<PORT>/api/student-panel/l1-road"
curl -s -o /dev/null -w "%{http_code}\n" "http://127.0.0.1:<PORT>/api/student-panel/runs?limit=50"
```

Expect **200**; `GET …/l1-road` → `schema` = `student_panel_l1_road_v1` (includes **`road_by_job_id_v1`**). `GET …/runs` → `l1_road_v1.schema` = `student_panel_l1_road_runs_overlay_v1` for the Level 1 UI merge.

## Truth notes (non-negotiable)

- **Single read** of `batch_scorecard.jsonl` in file order — **no** per-row Student store scan.  
- **E** = mean of persisted `expectancy_per_trade` (batch economic rollup).  
- **P** = mean of optional `student_l1_process_score_v1` when present; otherwise `avg_p_process_score` null and `process_leg: data_gap` for E-only A/B.  
- **No cross-fingerprint mixing:** each `fingerprint_sha256_40` bucket has its own baseline anchor.
