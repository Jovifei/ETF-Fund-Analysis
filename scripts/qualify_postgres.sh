#!/usr/bin/env bash
# qualify_postgres.sh -- isolated PostgreSQL 16 qualification drill.
#
# Proves on a throwaway instance that the Alembic chain can upgrade, downgrade,
# back up, restore and keep its data intact -- the deployment gate described in
# STATUS.md ("real PostgreSQL migration / backup / isolated restore").
#
# Safety model:
#   * Default mode starts a DISPOSABLE `docker run` container named
#     fund-decision-pg-qualify on 127.0.0.1:15432. It never touches the
#     production compose `db` service; this script never invokes
#     `docker compose` at all.
#   * The target database name is refused if it matches the production compose
#     default (`fund_decision`) unless --i-know-this-is-isolated is passed.
#   * The generated runtime password is only ever handed to the container env
#     and to the alembic subprocess via DATABASE_URL; every log line prints the
#     URL with the password masked as ***.
#   * The container (and its volume) is always removed on exit, including on
#     failure, unless --keep is passed.
#
# Usage:
#   scripts/qualify_postgres.sh [--json <path>] [--keep]
#                               [--db-url <url>] [--i-know-this-is-isolated]
#
#   --db-url <url>   Run against an externally provided PostgreSQL URL instead
#                    of starting a container (treated as isolated by
#                    convention). Container lifecycle is skipped; the URL must
#                    still be reachable. psql/pg_dump use local client binaries
#                    when available, otherwise one-shot postgres:16-alpine
#                    containers (loopback hosts are rewritten to
#                    host.docker.internal). Only plain (unencoded) userinfo is
#                    supported in the URL.
#   --json <path>    Write a machine-readable summary (steps, versions).
#   --keep           Keep the container after the run (default: always remove).
#
# Exit codes: 0 all steps passed; 1 step failure (failed step is named);
#             2 usage error.
#
# Known limitations:
#   * Docker is a hard requirement even in --db-url mode when local
#     psql/pg_dump binaries are absent (one-shot client containers are used
#     then); the docker daemon must be running either way.
#   * --db-url accepts only plain (non-percent-encoded) userinfo, no IPv6
#     literal hosts and no query parameters; '@' inside userinfo is rejected
#     up-front (URL-encode it as %40).
#   * The JSON report performs no JSON-string escaping of user-derived fields
#     (paths, URLs); values containing quotes or backslashes can render the
#     report invalid JSON.
#   * wipe_schema drops the URL's target schema (default: public); the
#     isolation-by-convention of --db-url is the blast-radius boundary, so
#     only ever point it at a disposable instance.
set -euo pipefail
umask 077   # dumps may contain real data in --db-url mode; artifacts stay 0600
script_path="$(cd "$(dirname "$0")" && pwd)/$(basename "$0")"
cd "$(dirname "$0")/.."

# --------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------
CONTAINER="fund-decision-pg-qualify"
PG_IMAGE="postgres:16-alpine"
HOST_PORT="15432"
PG_USER="qualify"
PG_DB="fund_qualify"
EXPECTED_HEAD="c4d5e6f7a8b9"
DOWNGRADE_REV="b3c4d5e6f7a8"
PROD_DB_NAME="fund_decision"   # docker-compose.yml POSTGRES_DB default
REPORT_DIR="deployment_reports"
READY_TIMEOUT_SECONDS=60

# --------------------------------------------------------------------------
# Globals (initialised for set -u)
# --------------------------------------------------------------------------
KEEP=0
DB_URL_MODE=0
ISOLATION_ACK=0
JSON_OUT=""
EXTERNAL_DB_URL=""

PYTHON_BIN=""
PG_PASSWORD=""
ALEMBIC_URL=""          # URL handed to the alembic subprocess (driver-qualified)
ALEMBIC_URL_MASKED=""   # precomputed once; all logs print this, never the raw URL
TARGET_DB=""            # parsed once from the URL; consumed by the safety guard
EXT_PSQL=""             # local psql binary, if any (db-url mode)
EXT_DUMP=""             # local pg_dump binary, if any (db-url mode)
EXT_USER=""
EXT_PASSWORD=""
EXT_HOST=""
EXT_HOST_CLIENT=""      # host as seen by one-shot client containers
EXT_PORT=""
EXT_DB=""
EXT_URL_CLIENT=""       # full URL as seen by one-shot client containers
DOCKER_HOST_ARGS=""     # intentional word splitting: extra docker run flags
MODE_LABEL="docker-container"

CURRENT_STEP=""
STEP_START=0
FAILED_STEP=""
JSON_STEPS=""
HEAD_REACHED=""
DUMP_FILE=""
RESTORE_LOG=""
BACKUP_SHA=""
BACKUP_BYTES=0
TBL_BEFORE=0 IDX_BEFORE=0 CON_BEFORE=0
TBL_AFTER=0 IDX_AFTER=0 CON_AFTER=0
SEED_RS_BEFORE=0 SEED_EL_BEFORE=0
SEED_RS_AFTER=0 SEED_EL_AFTER=0
STARTED_CONTAINER=0
RUN_START=0

COUNT_TABLES_SQL="SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast') AND c.relkind IN ('r', 'p')"
COUNT_INDEXES_SQL="SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast') AND c.relkind = 'i'"
COUNT_CONSTRAINTS_SQL="SELECT count(*) FROM pg_constraint con JOIN pg_namespace n ON n.oid = con.connamespace WHERE n.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast') AND con.contype IN ('p', 'u', 'f', 'c')"

# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------
log() { printf '[pg-qualify] %s\n' "$*"; }

now_ms() {
    local t
    if t="$(date +%s%N 2>/dev/null)"; then
        case "$t" in
            *[!0-9]*) printf '%s' $(( $(date +%s) * 1000 )) ;;
            *) printf '%s' $(( 10#$t / 1000000 )) ;;
        esac
    else
        printf '%s' $(( $(date +%s) * 1000 ))
    fi
}

# Print a connection URL with the password replaced by *** (no-op when the
# URL carries no userinfo password).
mask_url() {
    printf '%s' "$1" | sed -E 's#(://[^:/@]+:)[^@]*@#\1***@#'
}

human_size() {
    awk -v b="$1" 'BEGIN {
        if (b >= 1048576) printf "%.1f MiB", b / 1048576;
        else if (b >= 1024) printf "%.1f KiB", b / 1024;
        else printf "%d B", b;
    }'
}

require_number() {
    case "${1:-}" in
        '' | *[!0-9]*) log "ERROR: non-numeric query result: '${1:-}'"; return 1 ;;
    esac
}

# dbname segment of a postgres URL (RFC 3986: userinfo ends at the last '@').
url_dbname() {
    local rest path
    rest="${1#*://}"
    rest="${rest##*@}"          # host:port/db?query
    path="${rest#*/}"           # db?query
    path="${path%%\?*}"
    printf '%s' "$path"
}

# Rewrite loopback hosts so one-shot client containers can reach the host.
rewrite_loopback() {
    printf '%s' "$1" | sed -E \
        -e 's#@127\.0\.0\.1:#@host.docker.internal:#' \
        -e 's#@localhost:#@host.docker.internal:#'
}

# Qualify the driver for SQLAlchemy/psycopg3 (the app's DATABASE_URL scheme,
# cf. docker-compose.yml: postgresql+psycopg://...).
qualify_driver() {
    case "$1" in
        postgresql://* | postgres://*) printf 'postgresql+psycopg://%s' "${1#*://}" ;;
        *) printf '%s' "$1" ;;
    esac
}

# --------------------------------------------------------------------------
# Step bookkeeping: begin_step/end_step bracket a step; any failure inside a
# step aborts via set -e and the EXIT trap records CURRENT_STEP as failed.
# --------------------------------------------------------------------------
begin_step() {
    CURRENT_STEP="$1"
    STEP_START="$(now_ms)"
    log "step: $1"
}

end_step() {
    record_step "$CURRENT_STEP" "passed" $(( $(now_ms) - STEP_START ))
    CURRENT_STEP=""
}

record_step() { # name status duration_ms
    local obj
    obj="$(printf '{"name": "%s", "status": "%s", "duration_ms": %s}' "$1" "$2" "$3")"
    if [ -z "$JSON_STEPS" ]; then
        JSON_STEPS="$obj"
    else
        JSON_STEPS="$JSON_STEPS,$obj"
    fi
    log "step $1: $2 (${3} ms)"
}

# --------------------------------------------------------------------------
# PostgreSQL client helpers. Default mode shells into the disposable
# container (same style as scripts/backup_postgres.sh and
# scripts/restore_postgres.sh, which rely on the image's trusted local
# socket). db-url mode prefers local client binaries and falls back to
# one-shot client containers.
# --------------------------------------------------------------------------
ext_psql() { # args: psql options; SQL/dbname comes from callers
    # ON_ERROR_STOP mirrors the container path: without it a restore whose
    # DDL succeeds but whose COPYs partially fail would still exit 0.
    if [ -n "$EXT_PSQL" ]; then
        PGPASSWORD="$EXT_PASSWORD" "$EXT_PSQL" -v ON_ERROR_STOP=1 "$@" "$EXTERNAL_DB_URL"
    else
        # shellcheck disable=SC2086
        docker run --rm -i $DOCKER_HOST_ARGS -e PGPASSWORD="$EXT_PASSWORD" \
            "$PG_IMAGE" psql -v ON_ERROR_STOP=1 "$@" "$EXT_URL_CLIENT"
    fi
}

target_psql() { # args: psql options; reads SQL from -c args or stdin
    if [ "$DB_URL_MODE" -eq 0 ]; then
        docker exec -i "$CONTAINER" psql -v ON_ERROR_STOP=1 -U "$PG_USER" -d "$PG_DB" "$@"
    else
        ext_psql "$@"
    fi
}

psql_scalar() { # single SQL expression -> single value on stdout
    # tr -d '\r': native Windows psql.exe emits CRLF line endings.
    target_psql -t -A -c "$1" | tr -d '\r'
}

ext_dump() {
    if [ -n "$EXT_DUMP" ]; then
        PGPASSWORD="$EXT_PASSWORD" "$EXT_DUMP" --clean --if-exists \
            --no-owner --no-privileges -h "$EXT_HOST" -p "$EXT_PORT" \
            -U "$EXT_USER" "$EXT_DB"
    else
        # shellcheck disable=SC2086
        docker run --rm $DOCKER_HOST_ARGS -e PGPASSWORD="$EXT_PASSWORD" \
            "$PG_IMAGE" pg_dump --clean --if-exists --no-owner --no-privileges \
            -h "$EXT_HOST_CLIENT" -p "$EXT_PORT" -U "$EXT_USER" "$EXT_DB"
    fi
}

alembic_cmd() { # DATABASE_URL override is the only place the raw password travels
    DATABASE_URL="$ALEMBIC_URL" APP_ENV=development "$PYTHON_BIN" -m alembic "$@"
}

# --------------------------------------------------------------------------
# Steps
# --------------------------------------------------------------------------
toolchain_step() {
    begin_step "toolchain_check"

    # Docker is required in both modes: container lifecycle by default, or
    # one-shot client containers in --db-url mode when local psql/pg_dump
    # binaries are absent.
    command -v docker >/dev/null 2>&1 || { log "ERROR: docker CLI not found"; return 1; }
    docker version --format '{{.Server.Version}}' >/dev/null 2>&1 \
        || { log "ERROR: docker daemon unreachable"; return 1; }

    # Interpreter discovery: $PYTHON override, venv layouts, then PATH.
    if [ -n "${PYTHON:-}" ] && command -v "$PYTHON" >/dev/null 2>&1; then
        PYTHON_BIN="$PYTHON"
    elif [ -f ".venv/Scripts/python.exe" ]; then
        PYTHON_BIN=".venv/Scripts/python.exe"
    elif [ -f ".venv/bin/python" ]; then
        PYTHON_BIN=".venv/bin/python"
    elif command -v python3 >/dev/null 2>&1; then
        PYTHON_BIN="python3"
    elif command -v python >/dev/null 2>&1; then
        PYTHON_BIN="python"
    else
        log "ERROR: no python interpreter found (set \$PYTHON)"
        return 1
    fi
    log "python: $PYTHON_BIN"
    "$PYTHON_BIN" -c 'import alembic, sqlalchemy, psycopg' >/dev/null 2>&1 \
        || { log "ERROR: interpreter lacks alembic/sqlalchemy/psycopg"; return 1; }

    mkdir -p "$REPORT_DIR"
    if [ -n "$JSON_OUT" ]; then
        mkdir -p "$(dirname "$JSON_OUT")"
    fi

    if [ "$DB_URL_MODE" -eq 1 ]; then
        MODE_LABEL="external-db-url"
        ALEMBIC_URL="$(qualify_driver "$EXTERNAL_DB_URL")"
        EXT_URL_CLIENT="$(rewrite_loopback "$EXTERNAL_DB_URL")"
        # Parse userinfo/host/db for local or one-shot client tools.
        _rest="${EXTERNAL_DB_URL#*://}"
        _userinfo="${_rest%%@*}"
        _hostport="${_rest##*@}"
        _hostport="${_hostport%%\?*}"
        _hostport="${_hostport%%/*}"
        EXT_USER="${_userinfo%%:*}"
        case "$_userinfo" in
            *:*) EXT_PASSWORD="${_userinfo#*:}" ;;
            *) EXT_PASSWORD="" ;;
        esac
        EXT_HOST="${_hostport%%:*}"
        case "$_hostport" in
            *:*) EXT_PORT="${_hostport##*:}" ;;
            *) EXT_PORT="5432" ;;
        esac
        EXT_DB="$(url_dbname "$EXTERNAL_DB_URL")"
        case "$EXTERNAL_DB_URL" in
            *@127.0.0.1:* | *@localhost:*) DOCKER_HOST_ARGS="--add-host=host.docker.internal:host-gateway" ;;
        esac
        EXT_HOST_CLIENT="$(printf '%s' "$EXT_URL_CLIENT" | sed -E 's#.*://[^@]*@([^:/]+).*#\1#')"
        if command -v psql >/dev/null 2>&1 && command -v pg_dump >/dev/null 2>&1; then
            EXT_PSQL="$(command -v psql)"
            EXT_DUMP="$(command -v pg_dump)"
            log "external mode: using local psql/pg_dump clients"
        else
            case "$EXTERNAL_DB_URL" in
                *@*) : ;;
                *) log "ERROR: --db-url without userinfo credentials requires local psql/pg_dump client binaries"; return 1 ;;
            esac
            log "external mode: local psql/pg_dump not found; using one-shot $PG_IMAGE client containers"
            docker image inspect "$PG_IMAGE" >/dev/null 2>&1 || docker pull "$PG_IMAGE" >/dev/null
        fi
    else
        # Runtime password: openssl first, /dev/urandom fallback.
        if command -v openssl >/dev/null 2>&1 && PG_PASSWORD="$(openssl rand -hex 24 2>/dev/null)"; then
            :
        else
            PG_PASSWORD="$(head -c 24 /dev/urandom | od -An -tx1 | tr -d ' \n')"
        fi
        case "$PG_PASSWORD" in
            '' | *[!0-9a-f]*) log "ERROR: generated password is not hex"; return 1 ;;
        esac
        ALEMBIC_URL="postgresql+psycopg://${PG_USER}:${PG_PASSWORD}@127.0.0.1:${HOST_PORT}/${PG_DB}"
    fi

    # Parse and mask once, at construction. Everything printed afterwards uses
    # the precomputed masked URL, so the raw value only ever appears on the
    # construction lines and on the container-env/DATABASE_URL handoffs.
    ALEMBIC_URL_MASKED="$(mask_url "$ALEMBIC_URL")"
    TARGET_DB="$(url_dbname "$ALEMBIC_URL")"
    log "target database URL (password masked): $ALEMBIC_URL_MASKED"
    end_step
}

safety_guard_step() {
    begin_step "safety_guard"
    local target_db="$TARGET_DB"
    if [ "$target_db" = "$PROD_DB_NAME" ]; then
        if [ "$ISOLATION_ACK" -eq 1 ]; then
            log "WARNING: database '$target_db' matches the production compose default; proceeding only because --i-know-this-is-isolated was passed"
        else
            log "REFUSING: target database '$target_db' matches the production compose default ('$PROD_DB_NAME')"
            log "Pass --i-know-this-is-isolated only if this target is genuinely an isolated instance."
            return 1
        fi
    else
        log "isolation check OK: database '$target_db' does not match production default '$PROD_DB_NAME'"
    fi
    end_step
}

start_isolated_pg_step() {
    if [ "$DB_URL_MODE" -eq 1 ]; then
        record_step "start_isolated_pg" "skipped" 0
        begin_step "connect_external_db"
        local probe
        probe="$(psql_scalar 'SELECT 1')" || probe=""
        [ "$probe" = "1" ] || { log "ERROR: external database is not reachable"; return 1; }
        log "external database reachable"
        end_step
        return 0
    fi

    begin_step "start_isolated_pg"
    if docker container inspect "$CONTAINER" >/dev/null 2>&1; then
        log "ERROR: container name already in use; run: docker rm -f -v $CONTAINER"
        return 1
    fi
    docker image inspect "$PG_IMAGE" >/dev/null 2>&1 || docker pull "$PG_IMAGE"
    STARTED_CONTAINER=1
    local cid
    cid="$(docker run -d --name "$CONTAINER" \
        -e POSTGRES_PASSWORD="$PG_PASSWORD" \
        -e POSTGRES_USER="$PG_USER" \
        -e POSTGRES_DB="$PG_DB" \
        -p "127.0.0.1:${HOST_PORT}:5432" \
        "$PG_IMAGE")"
    [ -n "$cid" ] || { log "ERROR: docker run failed"; return 1; }

    local ready=0 i
    for i in $(seq 1 "$READY_TIMEOUT_SECONDS"); do
        if docker exec "$CONTAINER" pg_isready -U "$PG_USER" -d "$PG_DB" >/dev/null 2>&1; then
            ready=1
            break
        fi
        sleep 1
    done
    [ "$ready" -eq 1 ] || { log "ERROR: pg_isready timed out after ${READY_TIMEOUT_SECONDS}s"; return 1; }
    log "postgres ready at 127.0.0.1:${HOST_PORT} (container $CONTAINER, image $PG_IMAGE)"
    end_step
}

alembic_upgrade_head_step() {
    begin_step "alembic_upgrade_head"
    alembic_cmd upgrade head
    local head_line
    head_line="$(alembic_cmd current 2>/dev/null | tail -n 1)"
    HEAD_REACHED="$(printf '%s' "$head_line" | awk '{print $1}')"
    [ "$HEAD_REACHED" = "$EXPECTED_HEAD" ] \
        || { log "ERROR: alembic head is '$HEAD_REACHED', expected '$EXPECTED_HEAD'"; return 1; }
    log "alembic head verified: $HEAD_REACHED"
    end_step
}

alembic_downgrade_step() {
    begin_step "alembic_downgrade_prev"
    alembic_cmd downgrade "$DOWNGRADE_REV"
    local cur
    cur="$(alembic_cmd current 2>/dev/null | tail -n 1 | awk '{print $1}')"
    [ "$cur" = "$DOWNGRADE_REV" ] \
        || { log "ERROR: after downgrade alembic current is '$cur', expected '$DOWNGRADE_REV'"; return 1; }
    log "downgrade verified: $cur"
    end_step
}

alembic_upgrade_again_step() {
    begin_step "alembic_upgrade_again"
    alembic_cmd upgrade head
    local head_line
    head_line="$(alembic_cmd current 2>/dev/null | tail -n 1)"
    HEAD_REACHED="$(printf '%s' "$head_line" | awk '{print $1}')"
    [ "$HEAD_REACHED" = "$EXPECTED_HEAD" ] \
        || { log "ERROR: re-upgrade head is '$HEAD_REACHED', expected '$EXPECTED_HEAD'"; return 1; }
    log "re-upgrade verified: $HEAD_REACHED"
    end_step
}

seed_rows_step() {
    begin_step "seed_rows"
    target_psql <<'SQL'
INSERT INTO runtime_settings (key, value_json, description)
VALUES ('qualify_probe', '{"seed": "pg-qualify", "source": "qualify_postgres.sh"}', 'temporary qualification seed row; safe to delete');
INSERT INTO event_log (event_type, payload_json)
VALUES ('qualify.seed', '{"origin": "pg-qualify", "step": "seed"}');
SQL
    SEED_RS_BEFORE="$(psql_scalar "SELECT count(*) FROM runtime_settings WHERE key = 'qualify_probe'")"
    require_number "$SEED_RS_BEFORE" || return 1
    SEED_EL_BEFORE="$(psql_scalar "SELECT count(*) FROM event_log WHERE event_type = 'qualify.seed'")"
    require_number "$SEED_EL_BEFORE" || return 1
    [ "$SEED_RS_BEFORE" -ge 1 ] && [ "$SEED_EL_BEFORE" -ge 1 ] \
        || { log "ERROR: seed rows missing (runtime_settings=$SEED_RS_BEFORE, event_log=$SEED_EL_BEFORE)"; return 1; }
    log "seeded runtime_settings=$SEED_RS_BEFORE, event_log=$SEED_EL_BEFORE"
    end_step
}

capture_counts_before_step() {
    begin_step "capture_counts_before"
    TBL_BEFORE="$(psql_scalar "$COUNT_TABLES_SQL")"
    require_number "$TBL_BEFORE" || return 1
    IDX_BEFORE="$(psql_scalar "$COUNT_INDEXES_SQL")"
    require_number "$IDX_BEFORE" || return 1
    CON_BEFORE="$(psql_scalar "$COUNT_CONSTRAINTS_SQL")"
    require_number "$CON_BEFORE" || return 1
    log "pre-backup counts: tables=$TBL_BEFORE indexes=$IDX_BEFORE constraints=$CON_BEFORE"
    end_step
}

backup_dump_step() {
    begin_step "backup_dump"
    DUMP_FILE="$REPORT_DIR/pg-qualify-backup-${RUN_STAMP}.sql.gz"
    if [ "$DB_URL_MODE" -eq 0 ]; then
        docker exec "$CONTAINER" pg_dump --clean --if-exists --no-owner --no-privileges \
            -U "$PG_USER" "$PG_DB" | gzip -9 > "$DUMP_FILE"
    else
        ext_dump | gzip -9 > "$DUMP_FILE"
    fi
    [ -s "$DUMP_FILE" ] || { log "ERROR: dump file is empty: $DUMP_FILE"; return 1; }
    sha256sum "$DUMP_FILE" > "${DUMP_FILE}.sha256"
    BACKUP_SHA="$(awk '{print $1}' "${DUMP_FILE}.sha256")"
    BACKUP_BYTES="$(wc -c < "$DUMP_FILE" | tr -d ' ')"
    log "backup written: $DUMP_FILE ($(human_size "$BACKUP_BYTES"))"
    log "backup sha256: $BACKUP_SHA"
    if ! sha256sum -c "${DUMP_FILE}.sha256" >/dev/null 2>&1; then
        log "ERROR: sha256 verification FAILED for $DUMP_FILE"
        return 1
    fi
    log "backup sha256 verification: OK"
    end_step
}

wipe_schema_step() {
    begin_step "wipe_schema"
    target_psql <<'SQL'
DROP SCHEMA public CASCADE;
CREATE SCHEMA public;
SQL
    local remaining
    remaining="$(psql_scalar "$COUNT_TABLES_SQL")"
    require_number "$remaining" || return 1
    [ "$remaining" -eq 0 ] || { log "ERROR: wipe left $remaining tables behind"; return 1; }
    log "schema wiped; 0 non-system tables remain"
    end_step
}

restore_dump_step() {
    begin_step "restore_dump"
    RESTORE_LOG="$REPORT_DIR/pg-qualify-restore-${RUN_STAMP}.log"
    if ! gzip -dc "$DUMP_FILE" | target_psql > "$RESTORE_LOG" 2>&1; then
        log "ERROR: psql restore failed; tail of $RESTORE_LOG:"
        tail -n 30 "$RESTORE_LOG" >&2 || true
        return 1
    fi
    log "restore completed; full psql output: $RESTORE_LOG"
    end_step
}

verify_integrity_step() {
    begin_step "verify_integrity"
    TBL_AFTER="$(psql_scalar "$COUNT_TABLES_SQL")"
    require_number "$TBL_AFTER" || return 1
    IDX_AFTER="$(psql_scalar "$COUNT_INDEXES_SQL")"
    require_number "$IDX_AFTER" || return 1
    CON_AFTER="$(psql_scalar "$COUNT_CONSTRAINTS_SQL")"
    require_number "$CON_AFTER" || return 1
    log "post-restore counts: tables=$TBL_AFTER indexes=$IDX_AFTER constraints=$CON_AFTER"

    if [ "$TBL_AFTER" != "$TBL_BEFORE" ] || [ "$IDX_AFTER" != "$IDX_BEFORE" ] \
        || [ "$CON_AFTER" != "$CON_BEFORE" ]; then
        log "ERROR: pg_class counts differ (before: tables=$TBL_BEFORE indexes=$IDX_BEFORE constraints=$CON_BEFORE; after: tables=$TBL_AFTER indexes=$IDX_AFTER constraints=$CON_AFTER)"
        return 1
    fi

    SEED_RS_AFTER="$(psql_scalar "SELECT count(*) FROM runtime_settings WHERE key = 'qualify_probe'")"
    require_number "$SEED_RS_AFTER" || return 1
    SEED_EL_AFTER="$(psql_scalar "SELECT count(*) FROM event_log WHERE event_type = 'qualify.seed'")"
    require_number "$SEED_EL_AFTER" || return 1
    [ "$SEED_RS_AFTER" = "$SEED_RS_BEFORE" ] && [ "$SEED_EL_AFTER" = "$SEED_EL_BEFORE" ] \
        || { log "ERROR: seeded rows did not survive restore (runtime_settings=$SEED_RS_AFTER/$SEED_RS_BEFORE, event_log=$SEED_EL_AFTER/$SEED_EL_BEFORE)"; return 1; }
    log "seed rows survived restore: runtime_settings=$SEED_RS_AFTER, event_log=$SEED_EL_AFTER"
    log "integrity verification: PASSED"
    end_step
}

# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------
write_json() {
    local total_ms result
    total_ms=$(( $(now_ms) - RUN_START ))
    if [ "$FINAL_RC" -eq 0 ]; then result="passed"; else result="failed"; fi
    {
        printf '{\n'
        printf '  "generated_at": "%s",\n' "$(date +%Y-%m-%dT%H:%M:%S%z)"
        printf '  "mode": "%s",\n' "$MODE_LABEL"
        printf '  "versions": {"pg_image": "%s", "alembic_head": "%s"},\n' "$PG_IMAGE" "$HEAD_REACHED"
        printf '  "downgrade_revision": "%s",\n' "$DOWNGRADE_REV"
        printf '  "database_url_masked": "%s",\n' "$ALEMBIC_URL_MASKED"
        printf '  "steps": [%s],\n' "$JSON_STEPS"
        printf '  "summary": {"result": "%s", "failed_step": "%s", "container": "%s", "backup_file": "%s", "backup_bytes": %s, "backup_sha256": "%s", "tables_before": %s, "indexes_before": %s, "constraints_before": %s, "tables_after": %s, "indexes_after": %s, "constraints_after": %s, "seed_rows_runtime_settings": %s, "seed_rows_event_log": %s, "total_duration_ms": %s}\n' \
            "$result" "$FAILED_STEP" "$CONTAINER" "$DUMP_FILE" "$BACKUP_BYTES" "$BACKUP_SHA" \
            "$TBL_BEFORE" "$IDX_BEFORE" "$CON_BEFORE" \
            "$TBL_AFTER" "$IDX_AFTER" "$CON_AFTER" \
            "$SEED_RS_AFTER" "$SEED_EL_AFTER" "$total_ms"
        printf '}\n'
    } > "$JSON_OUT"
    log "json report written: $JSON_OUT"
}

print_summary() {
    local total_ms
    total_ms=$(( $(now_ms) - RUN_START ))
    log "================================================================"
    if [ "$FINAL_RC" -eq 0 ]; then
        log "QUALIFICATION RESULT: PASSED"
    else
        log "QUALIFICATION RESULT: FAILED (step: ${FAILED_STEP:-unknown})"
    fi
    log "  mode            : $MODE_LABEL"
    log "  container/image : $CONTAINER ($PG_IMAGE)"
    log "  database url    : $ALEMBIC_URL_MASKED"
    log "  alembic head    : ${HEAD_REACHED:-<not reached>}"
    log "  downgrade drill : $DOWNGRADE_REV (down -> up verified)"
    if [ -n "$DUMP_FILE" ]; then
        log "  backup          : $DUMP_FILE ($(human_size "$BACKUP_BYTES"))"
        log "  backup sha256   : $BACKUP_SHA (sidecar verified)"
    fi
    log "  restore verify  : tables $TBL_BEFORE->$TBL_AFTER, indexes $IDX_BEFORE->$IDX_AFTER, constraints $CON_BEFORE->$CON_AFTER"
    log "  seed survival   : runtime_settings=$SEED_RS_AFTER, event_log=$SEED_EL_AFTER"
    log "  total duration  : $(( total_ms / 1000 )).$(( total_ms % 1000 / 100 )) s"
    log "================================================================"
}

on_exit() {
    FINAL_RC=$?
    trap - EXIT

    if [ -n "$CURRENT_STEP" ]; then
        record_step "$CURRENT_STEP" "failed" $(( $(now_ms) - STEP_START ))
        FAILED_STEP="$CURRENT_STEP"
        CURRENT_STEP=""
    fi

    # Cleanup: always remove the disposable container (and its anonymous
    # volume) unless --keep; never in db-url mode (nothing was started).
    if [ "$DB_URL_MODE" -eq 0 ] && [ "$STARTED_CONTAINER" -eq 1 ]; then
        if [ "$KEEP" -eq 1 ]; then
            log "keeping container $CONTAINER (--keep); remove later with: docker rm -f -v $CONTAINER"
        else
            docker rm -f -v "$CONTAINER" >/dev/null 2>&1 || true
            log "cleanup: removed container $CONTAINER and its volume"
        fi
    fi

    if [ -n "$JSON_OUT" ]; then
        write_json || true
    fi
    print_summary

    if [ "$FINAL_RC" -ne 0 ]; then
        log "FAILED at step: ${FAILED_STEP:-unknown}"
    fi
    exit "$FINAL_RC"
}

# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
usage() {
    awk 'NR > 1 && $0 !~ /^#/ { exit } NR > 1 { sub(/^# ?/, ""); print }' "$0"
}

while [ $# -gt 0 ]; do
    case "$1" in
        --db-url)
            [ $# -ge 2 ] || { echo "--db-url requires a value" >&2; exit 2; }
            EXTERNAL_DB_URL="$2"; DB_URL_MODE=1; shift 2 ;;
        --keep) KEEP=1; shift ;;
        --json)
            [ $# -ge 2 ] || { echo "--json requires a path" >&2; exit 2; }
            JSON_OUT="$2"; shift 2 ;;
        --i-know-this-is-isolated) ISOLATION_ACK=1; shift ;;
        -h | --help) usage; exit 0 ;;
        *) echo "unknown argument: $1" >&2; usage >&2; exit 2 ;;
    esac
done

RUN_START="$(now_ms)"
RUN_STAMP="$(date +%Y%m%d_%H%M%S)"
FINAL_RC=0
trap on_exit EXIT

toolchain_step
safety_guard_step
start_isolated_pg_step
alembic_upgrade_head_step
alembic_downgrade_step
alembic_upgrade_again_step
seed_rows_step
capture_counts_before_step
backup_dump_step
wipe_schema_step
restore_dump_step
verify_integrity_step

log "all qualification steps passed"
exit 0
