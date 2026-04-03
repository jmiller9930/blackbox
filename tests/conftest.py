"""Default env for tests: no live Ollama calls unless a test overrides."""
import os

os.environ.setdefault("ANNA_USE_LLM", "0")
# Anna preflight (Pyth + market_data.db) is enforced in runtime; tests use fixtures without live pipeline.
os.environ.setdefault("ANNA_SKIP_PREFLIGHT", "1")
# Heavy math stack (statsmodels/arch/sklearn) off unless a test enables it.
os.environ.setdefault("ANNA_MATH_ENGINE_FULL", "0")
# Avoid writing execution_request_v1 rows during unrelated tests (enable per test if needed).
os.environ.setdefault("ANNA_AUTO_EXECUTION_REQUEST", "0")
# Never auto-approve / auto-run execution in the suite unless a test sets it.
os.environ.setdefault("ANNA_TRADER_MODE_AUTO_EXECUTE", "0")
# Karpathy daemon `--once` tests should not run full analysis→Jack unless a test enables it.
os.environ.setdefault("ANNA_KARPATHY_PAPER_HARNESS_EACH_TICK", "0")
