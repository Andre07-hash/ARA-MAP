#!/bin/zsh
# Corre todas las comprobaciones del proyecto y resume el resultado.
#
#   ./verificar.sh            comprobaciones que no necesitan nada instalado
#   ./verificar.sh --todo     añade linter, tipos y pruebas de navegador
#
# Las herramientas de desarrollo viven en .venv-dev y son opcionales: la
# aplicación en sí no depende de ellas.

cd "$(dirname "$0")" || exit 1
TODO=${1:-}
FALLOS=0

seccion() { echo ""; echo "── $1 ──"; }
resultado() {
  if [ "$1" -eq 0 ]; then echo "   OK   $2"; else echo "   FALLA  $2"; FALLOS=$((FALLOS + 1)); fi
}

seccion "Pruebas unitarias e integración (Python del sistema)"
python3 -m unittest discover -s tests -t . 2>&1 | tail -3
resultado ${pipestatus[1]} "suite de Python"

seccion "Compatibilidad con el Python que trae macOS"
if [ -x /usr/bin/python3 ]; then
  /usr/bin/python3 -m unittest discover -s tests -t . > /dev/null 2>&1
  resultado $? "suite completa en $( /usr/bin/python3 -V 2>&1 )"
else
  echo "   (omitido: no hay /usr/bin/python3)"
fi

seccion "Lógica de mapa y comparación (JavaScript)"
node --test tests/js/*.test.mjs 2>&1 | tail -3
resultado ${pipestatus[1]} "pruebas de JavaScript"

if [ "$TODO" = "--todo" ]; then
  seccion "Linter y tipos"
  if [ -x .venv-dev/bin/ruff ]; then
    .venv-dev/bin/ruff check server/ tests/ --output-format=concise | tail -3
    resultado ${pipestatus[1]} "ruff"
    .venv-dev/bin/mypy server/ 2>&1 | tail -2
    resultado ${pipestatus[1]} "mypy"
    .venv-dev/bin/python -m coverage run -m unittest discover -s tests -t . > /dev/null 2>&1
    .venv-dev/bin/python -m coverage report | tail -2
    resultado ${pipestatus[1]} "cobertura (mínimo 80%)"
    rm -f .coverage
  else
    echo "   (omitido: no existe .venv-dev; crea uno con python3 -m venv .venv-dev)"
  fi

  seccion "Pruebas de navegador"
  echo "   Requieren la aplicación corriendo y Chrome instalado:"
  echo "     ARA_MAP_DB=/tmp/ara-e2e.db python3 -m server.app"
  echo "     cd tests/e2e && npm install && npm test"
fi

echo ""
if [ $FALLOS -eq 0 ]; then
  echo "Todo en orden."
else
  echo "$FALLOS comprobación(es) con fallas."
fi
exit $FALLOS
