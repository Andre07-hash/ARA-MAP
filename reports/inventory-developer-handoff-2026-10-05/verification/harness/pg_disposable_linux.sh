#!/bin/sh
# Linux variant of pg_disposable.sh (Stage 2 verifier machine: root user, PG 16 from apt).
# A throwaway cluster in a mktemp dir owned by `postgres` (initdb refuses root),
# 127.0.0.1:55433 only, trust auth for the fictional role `verifier`, torn down on exit.
# The developer's cluster on 55432 is never touched.
#
#   harness/pg_disposable_linux.sh -- <command> [args...]
#   harness/pg_disposable_linux.sh --check
#
# The child sees ONLY ARA_MAP_TEST_DATABASE_URL for this cluster. DATABASE_URL and
# ARA_MAP_DATABASE_URL are removed; .env.local is never read; nothing here runs
# scripts/migrate_cloud.py or scripts/setup_cloud.py.
set -eu

PGBIN=/usr/lib/postgresql/16/bin
PORT=55433
DB=ara_verify
ROLE=verifier
AS_PG="runuser -u postgres --"

if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "port $PORT already in use; refusing" >&2
  exit 2
fi

WORK=$(mktemp -d /tmp/ara-pg-verify.XXXXXX)
chown postgres "$WORK"
chmod 700 "$WORK"
cleanup() {
  $AS_PG "$PGBIN/pg_ctl" -D "$WORK/data" -m immediate stop >/dev/null 2>&1 || true
  rm -rf "$WORK"
  echo "[pg_disposable_linux] torn down $WORK" >&2
}
trap cleanup EXIT INT TERM

$AS_PG "$PGBIN/initdb" -D "$WORK/data" -U "$ROLE" --auth=trust --encoding=UTF8 --locale=C >/dev/null 2>"$WORK/initdb.err" \
  || { cat "$WORK/initdb.err" >&2; exit 3; }
$AS_PG "$PGBIN/pg_ctl" -D "$WORK/data" -l "$WORK/server.log" -w \
  -o "-p $PORT -k $WORK -c listen_addresses=127.0.0.1 -c fsync=off" start >/dev/null
"$PGBIN/createdb" -h 127.0.0.1 -p "$PORT" -U "$ROLE" -E UTF8 "$DB"

URL="postgresql://$ROLE@127.0.0.1:$PORT/$DB"
echo "[pg_disposable_linux] $("$PGBIN/postgres" --version) at 127.0.0.1:$PORT db=$DB dir=$WORK" >&2

if [ "${1:-}" = "--check" ]; then
  "$PGBIN/psql" "$URL" -Atc "select current_database(), current_user, inet_server_addr(), inet_server_port(), pg_encoding_to_char(encoding), version() from pg_database where datname = current_database()"
  exit 0
fi
[ "${1:-}" = "--" ] && shift
[ "$#" -gt 0 ] || { echo "usage: $0 -- <command> | --check" >&2; exit 2; }

env -u DATABASE_URL -u ARA_MAP_DATABASE_URL ARA_MAP_TEST_DATABASE_URL="$URL" "$@"
