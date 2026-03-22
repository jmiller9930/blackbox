#!/usr/bin/env bash
# Apply Phase 1.5 then Phase 1.6 SQLite schemas (controlled execution tables/views).
# Usage: from repo root — ./scripts/init_phase1_6_sqlite.sh
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DB="${BLACKBOX_SQLITE_PATH:-${ROOT}/data/sqlite/blackbox.db}"
S5="${ROOT}/data/sqlite/schema_phase1_5.sql"
S6="${ROOT}/data/sqlite/schema_phase1_6.sql"
for f in "$S5" "$S6"; do
  if [[ ! -f "$f" ]]; then
    echo "error: missing $f" >&2
    exit 1
  fi
done
mkdir -p "$(dirname "$DB")"
sqlite3 "$DB" <"$S5"
sqlite3 "$DB" <"$S6"
echo "Applied Phase 1.5 + 1.6 schema to: $DB"
chmod 600 "$DB" 2>/dev/null || true
