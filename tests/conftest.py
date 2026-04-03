"""Default env for tests: no live Ollama calls unless a test overrides."""
import os

os.environ.setdefault("ANNA_USE_LLM", "0")
# Anna preflight (Pyth + market_data.db) is enforced in runtime; tests use fixtures without live pipeline.
os.environ.setdefault("ANNA_SKIP_PREFLIGHT", "1")
# Heavy math stack (statsmodels/arch/sklearn) off unless a test enables it.
os.environ.setdefault("ANNA_MATH_ENGINE_FULL", "0")
