"""
**Single** host file for **external OpenAI** API access (env name ``OPENAI_API_KEY``).

* Default path: ``~/.blackbox_secrets/openai.env`` (one file; ``chmod 600``;
  directory ``~/.blackbox_secrets`` typically ``700``).
* Override: set environment variable ``BLACKBOX_OPENAI_ENV_FILE`` to an absolute
  or user-relative path. Pattern Game / Flask and ``external_openai_adapter_v1``
  use this contract only—do not duplicate alternate key stores for OpenAI in code.
"""

from __future__ import annotations

import os

# Environment variable holding the live API key (read by the adapter, never committed).
EXTERNAL_API_OPENAI_KEY_ENV = "OPENAI_API_KEY"
# If set, path to a single file containing e.g. ``export OPENAI_API_KEY='…'`` (see below).
EXTERNAL_API_OPENAI_ENV_FILE_ENV = "BLACKBOX_OPENAI_ENV_FILE"
# When ``BLACKBOX_OPENAI_ENV_FILE`` is unset, this path under the user home is the default.
DEFAULT_HOME_SUBPATH = (".blackbox_secrets", "openai.env")


def default_external_openai_env_file_v1() -> str:
    """``~/.blackbox_secrets/openai.env`` (single canonical file when no override is set)."""
    return os.path.join(os.path.expanduser("~"), *DEFAULT_HOME_SUBPATH)


def resolved_external_openai_env_file_v1() -> str:
    """
    The one host file used for OpenAI: ``BLACKBOX_OPENAI_ENV_FILE`` or
    :func:`default_external_openai_env_file_v1`.
    """
    p = (os.environ.get(EXTERNAL_API_OPENAI_ENV_FILE_ENV) or "").strip()
    if p:
        return os.path.expanduser(p)
    return default_external_openai_env_file_v1()


__all__ = [
    "DEFAULT_HOME_SUBPATH",
    "EXTERNAL_API_OPENAI_ENV_FILE_ENV",
    "EXTERNAL_API_OPENAI_KEY_ENV",
    "default_external_openai_env_file_v1",
    "resolved_external_openai_env_file_v1",
]
