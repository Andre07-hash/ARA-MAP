#!/bin/zsh
# Doble clic para abrir ARA Map.
#
# Todo corre en esta Mac. No hay que instalar nada: la librería para leer
# Excel viene incluida en la carpeta vendor/python.

cd "$(dirname "$0")" || exit 1

pausa_y_salir() {
  echo ""
  echo "Presiona Enter para cerrar esta ventana."
  read -r _
  exit 1
}

# Busca un Python 3.9 o mayor. No se confía en el primer "python3" del PATH:
# en una Mac recién configurada ese suele ser el de Apple, y puede convivir con
# otras instalaciones. Se prueban todos y se usa el primero que sirva.
CANDIDATOS=(
  "$(command -v python3 2>/dev/null)"
  /opt/homebrew/bin/python3
  /usr/local/bin/python3
  /usr/bin/python3
  /opt/homebrew/bin/python3.13
  /opt/homebrew/bin/python3.12
  /opt/homebrew/bin/python3.11
  /Library/Frameworks/Python.framework/Versions/Current/bin/python3
)

PYTHON=""
for candidato in "${CANDIDATOS[@]}"; do
  [ -n "$candidato" ] && [ -x "$candidato" ] || continue
  if "$candidato" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null; then
    PYTHON="$candidato"
    break
  fi
done

if [ -z "$PYTHON" ]; then
  echo "No se encontró Python 3.9 o superior en esta Mac."
  echo ""
  echo "Qué hacer:"
  echo "  1. Abre la App Store o https://www.python.org/downloads/"
  echo "  2. Instala Python 3 (cualquier versión 3.9 o más nueva)"
  echo "  3. Vuelve a hacer doble clic en este archivo"
  pausa_y_salir
fi

# Comprobación real: que la aplicación pueda leer un archivo de Excel.
if ! "$PYTHON" -c 'import sys; sys.path.insert(0, "."); import server, openpyxl' 2>/dev/null; then
  echo "La aplicación no pudo cargar la librería para leer archivos de Excel."
  echo ""
  echo "Python encontrado: $PYTHON"
  echo "Se esperaba encontrarla en: $(pwd)/vendor/python/openpyxl"
  echo ""
  if [ ! -d "vendor/python/openpyxl" ]; then
    echo "Esa carpeta no existe. Es probable que la copia de la aplicación esté"
    echo "incompleta: vuelve a copiar la carpeta ARA Map completa."
  else
    echo "La carpeta existe pero no se pudo importar. Detalle del error:"
    "$PYTHON" -c 'import sys; sys.path.insert(0, "."); import server, openpyxl' 2>&1 | tail -5
  fi
  pausa_y_salir
fi

echo "ARA Map"
echo "Python: $PYTHON"
echo ""

"$PYTHON" -m server.app
ESTADO=$?

# Un cierre limpio (Ctrl+C) no debe dejar la ventana esperando.
if [ $ESTADO -ne 0 ] && [ $ESTADO -ne 130 ]; then
  echo ""
  echo "La aplicación se cerró de forma inesperada (código $ESTADO)."
  pausa_y_salir
fi
