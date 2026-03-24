"""Default env for tests: no live Ollama calls unless a test overrides."""
import os

os.environ.setdefault("ANNA_USE_LLM", "0")
