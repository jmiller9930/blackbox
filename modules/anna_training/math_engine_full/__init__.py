"""
Full quantitative stack for Anna training math engine (opt-in heavy dependencies).

Requires: numpy, pandas, scipy, statsmodels, arch, scikit-learn (see requirements.txt).

Gate analyst path with env ``ANNA_MATH_ENGINE_FULL=1``. CLI ``math-engine-full`` always runs the stack.
"""

from __future__ import annotations

from modules.anna_training.math_engine_full.stack import (
    FULL_STACK_VERSION,
    full_stack_fact_lines,
    run_full_math_stack,
    training_full_stack_env_enabled,
)

__all__ = [
    "FULL_STACK_VERSION",
    "full_stack_fact_lines",
    "run_full_math_stack",
    "training_full_stack_env_enabled",
]
