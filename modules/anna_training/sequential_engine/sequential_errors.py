"""Errors for sequential_engine (loud failures on corruption)."""


class CorruptionError(ValueError):
    """Duplicate market_event_id with differing payload — data corruption suspected."""

    pass
