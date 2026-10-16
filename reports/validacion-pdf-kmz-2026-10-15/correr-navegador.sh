#!/bin/bash
# Runs the browser suites named by issue #51, each against its own fresh,
# disposable local server, and records time, exit code and peak RSS.
#
#   reports/validacion-pdf-kmz-2026-10-15/correr-navegador.sh EVIDENCIA_DIR [suite ...]
#
# Never inherits a hosted database: the provider variables are cleared first.
# Chromium comes from CHROMIUM (default /opt/pw-browsers/chromium).
set -u
cd "$(dirname "$0")/../../tests/e2e" || exit 1
EVID=${1:?carpeta de evidencia}; shift
mkdir -p "$EVID"
unset ARA_MAP_DATABASE_URL DATABASE_URL ARA_MAP_READ_ONLY SUPABASE_URL SUPABASE_SERVICE_ROLE_KEY ARA_MAP_ARCHIVOS
export CHROMIUM=${CHROMIUM:-/opt/pw-browsers/chromium}
PY=${PYTHON:-python3}
SUITES=${*:-"tabla-elegir tabla-subidas tabla-abrir-pdf tabla-archivos archivos-recorridos archivos-alcance tabla-identidad tabla-seleccion tabla-mapa tabla-mapa-paneles recorrido-completo"}
medir() { # name, command...
  local nombre=$1; shift
  local t0=$(date +%s)
  "$PY" - "$@" > "$EVID/$nombre.log" 2>&1 <<'PYEOF'
import resource, subprocess, sys
rc = subprocess.run(sys.argv[1:]).returncode
print(f"RSS_MAX_HIJOS_MIB={resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss/1024:.1f}")
sys.exit(rc)
PYEOF
  local rc=$?
  echo "$nombre rc=$rc segundos=$(( $(date +%s) - t0 )) $(grep -o 'RSS_MAX_HIJOS_MIB=.*' "$EVID/$nombre.log")" | tee -a "$EVID/resumen.txt"
}
con_servidor() { # name, port, extra-server-args, node-file
  local nombre=$1 puerto=$2 extra=$3 archivo=$4
  local dir; dir=$(mktemp -d /tmp/ara-qa-srv-XXXXXX)
  "$PY" tabla_servidor.py --puerto "$puerto" --carpeta "$dir/inst" $extra > "$dir/srv.log" 2>&1 &
  local pid=$!
  for _ in $(seq 1 120); do grep -q LISTO "$dir/srv.log" 2>/dev/null && break; sleep 0.5; done
  local bd; bd=$(sed -n 's/^BD //p' "$dir/srv.log")
  ARA_URL="http://127.0.0.1:$puerto" ARA_BD="${bd:-$dir/inst/desechable.db}" medir "$nombre" node "$archivo"
  kill "$pid" 2>/dev/null; wait "$pid" 2>/dev/null; rm -rf "$dir"
}
for s in $SUITES; do
  case $s in
    tabla-elegir)        ELEGIR_PUERTO=8581 medir "$s" node "$s.mjs" ;;
    tabla-subidas)       SUBIDAS_PUERTO=8582 medir "$s" node "$s.mjs" ;;
    tabla-abrir-pdf)     ABRIR_PUERTO=8583 medir "$s" node "$s.mjs" ;;
    tabla-seleccion)     SELECCION_PUERTO=8584 medir "$s" node "$s.mjs" ;;
    tabla-mapa)          MAPA_PUERTO=8585 medir "$s" node "$s.mjs" ;;
    tabla-mapa-paneles)  MAPA_PUERTO=8586 medir "$s" node "$s.mjs" ;;
    archivos-recorridos) ARCHIVOS_PUERTO=8587 medir "$s" node "$s.mjs" ;;
    archivos-alcance)    ARCHIVOS_PUERTO=8588 medir "$s" node "$s.mjs" ;;
    recorrido-completo)  RECORRIDO_PUERTO=8589 medir "$s" node "$s.mjs" ;;
    recorrido-completo-postgres)
      RECORRIDO_BD=postgres RECORRIDO_PUERTO=8590 medir "$s" node recorrido-completo.mjs ;;
    tabla-archivos)      con_servidor "$s" 8591 "" tabla-archivos.mjs ;;
    tabla-identidad)     con_servidor "$s" 8592 "--registros 4200" tabla-identidad.mjs ;;
    *) node "$s.mjs" > "$EVID/$s.log" 2>&1; echo "$s rc=$?" | tee -a "$EVID/resumen.txt" ;;
  esac
done
