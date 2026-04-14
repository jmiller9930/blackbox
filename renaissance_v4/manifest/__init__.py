"""Strategy manifest — validation and resolution against the plugin catalog (v1 skeleton)."""

from renaissance_v4.manifest.validate import validate_manifest_against_catalog
from renaissance_v4.manifest.runtime import build_signals_from_manifest

__all__ = ["validate_manifest_against_catalog", "build_signals_from_manifest"]
