#!/usr/bin/env bash
# Atomic local backup; no retention deletion and no production reconfiguration.
set -euo pipefail
umask 077
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
compose=(docker compose)
backup_dir="${BACKUP_DIR:-$ROOT/backups}"
project_directory=""
while (($#)); do
  case "$1" in
    --compose-file|--env-file)
      (($# >= 2)) || { echo "missing path argument" >&2; exit 2; }
      [[ -f "$2" ]] || { echo "configuration file missing" >&2; exit 2; }
      resolved="$(realpath -- "$2")"
      if [[ "$1" == --compose-file ]]; then
        compose+=(-f "$resolved")
        [[ -n "$project_directory" ]] || project_directory="$(dirname "$resolved")"
      else
        compose+=(--env-file "$resolved")
      fi
      shift 2 ;;
    --project-name)
      if (($# < 2)) || [[ ! "$2" =~ ^[a-z0-9][a-z0-9_-]*$ ]]; then
        echo "invalid project name" >&2; exit 2
      fi
      compose+=(-p "$2"); shift 2 ;;
    --backup-dir)
      if (($# < 2)) || [[ -z "$2" ]]; then
        echo "missing backup directory" >&2; exit 2
      fi
      backup_dir="$(realpath -m -- "$2")"; shift 2 ;;
    *) echo "usage: backup_postgres.sh [--compose-file FILE] [--project-name NAME] [--env-file FILE] [--backup-dir DIR]" >&2; exit 2 ;;
  esac
done
[[ -z "$project_directory" ]] || compose+=(--project-directory "$project_directory")
cd "$ROOT"
[[ ! -L "$backup_dir" ]] || { echo "symlink backup directory rejected" >&2; exit 2; }
mkdir -p -- "$backup_dir"
chmod 700 "$backup_dir"
backup_dir="$(realpath -- "$backup_dir")"
stamp="$(date +%Y%m%d_%H%M%S)"
pending="$(mktemp -d "$backup_dir/.pending-${stamp}-XXXXXX")"
nonce="${pending##*-}"
file="$backup_dir/fund_decision_${stamp}_${nonce}.sql.gz"
checksum_published=false
cleanup() {
  status=$?
  # Only this invocation's unpublished files are removed. Existing backups
  # (including rollback archives) are never pruned by a backup operation.
  if [[ "$status" != 0 && "$checksum_published" == true && ! -f "$file" ]]; then rm -f -- "${file}.sha256"; fi
  rm -rf -- "$pending"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
# The database identity expands inside the container, never on the host.
# shellcheck disable=SC2016
"${compose[@]}" exec -T db sh -c 'pg_dump --clean --if-exists --no-owner --no-privileges -U "$POSTGRES_USER" "$POSTGRES_DB"' | gzip -9 > "$pending/archive.sql.gz"
gzip -t "$pending/archive.sql.gz"
bytes="$(gzip -cd "$pending/archive.sql.gz" | wc -c)"
((bytes > 0)) || { echo "empty database dump rejected" >&2; exit 2; }
hash="$(sha256sum "$pending/archive.sql.gz" | cut -d' ' -f1)"
printf '%s  %s\n' "$hash" "${file##*/}" > "$pending/archive.sha256"
chmod 600 "$pending/archive.sql.gz" "$pending/archive.sha256"
# Checksum is published first; an archive is visible only after pg_dump,
# compression and validation succeed. Same-disk hard links refuse overwrite.
[[ ! -e "$file" && ! -e "${file}.sha256" ]] || { echo "backup name collision" >&2; exit 2; }
ln -- "$pending/archive.sha256" "${file}.sha256"
checksum_published=true
ln -- "$pending/archive.sql.gz" "$file"
printf '%s\n' "$file"
