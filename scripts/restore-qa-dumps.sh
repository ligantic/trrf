#!/usr/bin/env bash

set -Eeuo pipefail

usage() {
  cat <<EOF
Usage: $0 <primary-dump.sql> <clinical-dump.sql>

Replace the local TRRF primary and clinical databases with plain SQL pg_dump
files. Both target databases are named webapp and are owned by webapp.

The source dumps may use PostgreSQL 17 psql directives and Azure PostgreSQL
roles. The restore removes Azure ACL statements, maps pgadmin and
azure_pg_admin ownership to webapp, and runs each restore in one transaction.
EOF
}

log() {
  printf '\033[0;32m%s\033[0m\n' "$*" >&2
}

fail() {
  printf '\033[0;31mERROR: %s\033[0m\n' "$*" >&2
  exit 1
}

if [[ $# -ne 2 ]] || [[ "${1:-}" == "--help" ]]; then
  usage
  [[ "${1:-}" == "--help" ]] && exit 0
  exit 1
fi

primary_dump=$(realpath "$1")
clinical_dump=$(realpath "$2")

[[ -r "$primary_dump" ]] || fail "Primary dump is not readable: $primary_dump"
[[ -r "$clinical_dump" ]] || fail "Clinical dump is not readable: $clinical_dump"

grep -q '^-- PostgreSQL database dump$' "$primary_dump" || fail "Primary file is not a plain PostgreSQL dump"
grep -q '^-- PostgreSQL database dump$' "$clinical_dump" || fail "Clinical file is not a plain PostgreSQL dump"
grep -q '^-- PostgreSQL database dump complete$' "$primary_dump" || fail "Primary dump is incomplete"
grep -q '^-- PostgreSQL database dump complete$' "$clinical_dump" || fail "Clinical dump is incomplete"

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$repo_root"

docker compose up -d db clinicaldb

primary_container=$(docker compose ps -q db)
clinical_container=$(docker compose ps -q clinicaldb)
runserver_container=$(docker compose ps -q runserver)

[[ -n "$primary_container" ]] || fail "Primary database container is unavailable"
[[ -n "$clinical_container" ]] || fail "Clinical database container is unavailable"

if [[ -n "$runserver_container" ]]; then
  log "Stopping Django before replacing its databases"
  docker stop "$runserver_container" >/dev/null
fi

log_directory=$(mktemp -d)
trap 'rm -rf "$log_directory"' EXIT

normalize_dump() {
  sed -E \
    -e '/^\\(un)?restrict /d' \
    -e '/^SET transaction_timeout = /d' \
    -e '/^GRANT /d' \
    -e '/^REVOKE /d' \
    -e 's/ OWNER TO (pgadmin|azure_pg_admin);$/ OWNER TO webapp;/' \
    "$1"
}

restore_database() {
  local label=$1
  local container=$2
  local dump_file=$3
  local restore_log="$log_directory/$label.log"

  log "Replacing $label database from $dump_file"
  docker exec "$container" dropdb -U webapp --force --if-exists webapp
  docker exec "$container" createdb -U webapp -O webapp webapp

  if ! normalize_dump "$dump_file" \
    | docker exec -i "$container" psql \
        -X -U webapp -d webapp -v ON_ERROR_STOP=1 --single-transaction \
        >"$restore_log" 2>&1; then
    tail -80 "$restore_log" >&2
    fail "$label database restore failed"
  fi
}

validate_database() {
  local label=$1
  local container=$2
  local dump_file=$3
  local expected_tables
  local actual_tables
  local non_webapp_tables

  expected_tables=$(grep -c '^CREATE TABLE public\.' "$dump_file")
  actual_tables=$(docker exec "$container" psql -X -U webapp -d webapp -Atc \
    "SELECT count(*) FROM pg_catalog.pg_tables WHERE schemaname = 'public'")
  non_webapp_tables=$(docker exec "$container" psql -X -U webapp -d webapp -Atc \
    "SELECT count(*) FROM pg_catalog.pg_tables WHERE schemaname = 'public' AND tableowner <> 'webapp'")

  [[ "$actual_tables" == "$expected_tables" ]] \
    || fail "$label table count mismatch: expected $expected_tables, restored $actual_tables"
  [[ "$non_webapp_tables" == "0" ]] \
    || fail "$label has $non_webapp_tables tables not owned by webapp"

  docker exec "$container" psql -X -U webapp -d webapp -Atc \
    "SELECT 1 FROM public.django_migrations LIMIT 1" >/dev/null
  log "$label database validated: $actual_tables tables owned by webapp"
}

restore_database "primary" "$primary_container" "$primary_dump"
restore_database "clinical" "$clinical_container" "$clinical_dump"
validate_database "primary" "$primary_container" "$primary_dump"
validate_database "clinical" "$clinical_container" "$clinical_dump"

log "QA database restore completed"
log "Start Django or launch the VS Code debugger when ready"
