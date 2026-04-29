# Learning validation

System must generalize across similar setups, not exact matches.

Pattern similarity must be distance-based and predictive, not categorical.

Use `scripts/analyze_gt051_generalization_v1.py` (or `scripts/run_trade_cycle_gt048_v1.py --gt051-report`) on `runtime/gt048_cycle/<job-id>/student_learning_records_v1.jsonl` after a GT048/GT050-style cycle. Large lab replays may need explicit governance floors (for example `--promotion-e-min`) so rows can PROMOTE under slightly negative batch expectancy.

Learning is based on triple-barrier outcomes (TP/SL/time), validated via walk-forward testing (`scripts/run_trade_cycle_gt048_v1.py --enable-labels --walk-forward --gt055-report`, plus `scripts/analyze_gt055_walk_forward_v1.py`).
