#!/usr/bin/env bash
# Create or upgrade BLACK BOX SQLite DB from schema_phase1_5.sql.
# Usage: from repo root — ./scripts/init_phase1_5_sqlite.sh
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DB="${BLACKBOX_SQLITE_PATH:-${ROOT}/data/sqlite/blackbox.db}"
SCHEMA="${ROOT}/data/sqlite/schema_phase1_5.sql"
mkdir -p "$(dirname "$DB")"
if [[ ! -f "$SCHEMA" ]]; then
  echo "error: missing $SCHEMA" >&2
  exit 1
fi
sqlite3 "$DB" <"$SCHEMA"
echo "Applied schema to: $DB"
chmod 600 "$DB" 2>/dev/null || true
