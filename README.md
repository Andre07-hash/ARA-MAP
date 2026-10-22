# ARA Map

Portal privado para registrar terrenos, editar su tabla y adjuntar PDF o JPG y KMZ o KML.

**Sitio vigente:** [ara-map-piloto.onrender.com](https://ara-map-piloto.onrender.com/).
Este sitio es el proyecto definitivo; se mejora con cambios pequeños aunque su
nombre conserve «piloto».

## Código y desarrollo

Repositorio: [Andre07-hash/ARA-MAP](https://github.com/Andre07-hash/ARA-MAP).
La rama **`main`** es la base única para el trabajo nuevo y la rama de Render.
Las entregas aceptadas del antiguo piloto se conservan con su historial.
No hay división vigente por equipos A/B.

- [Guía para developers](docs/DESARROLLO.md): clon, entorno local, pruebas,
  pull requests, permisos y publicación.
- [Reglas compartidas para agentes](AGENTS.md).
- [Asistente IA: pausa y punto de reanudación](reports/asistente-ia-pausa-2026-10-20/README.md).
  Desarrollo conservado fuera de `main`; no activarlo ni publicarlo sin una
  nueva instrucción del propietario.
- [Transición al proyecto definitivo](reports/project-definitive-2026-10-13/START_HERE.md).

## Uso del portal

El responsable administra las cuentas. El administrador crea bases de trabajo
y concede accesos; el operador ve y edita las bases que tiene asignadas.
No hay registro público ni restablecimiento de contraseña por el propio usuario.

1. Inicia sesión con tu cuenta.
2. Elige una base y captura o edita las filas de terrenos.
3. Adjunta archivos mediante **Elegir PDF o JPG…** y **Elegir KMZ o KML…** en las celdas.
4. Alterna **Tabla / Mapa** para ver los terrenos de la vista y sus filtros.
5. En el mapa elige **Claro / Satélite / Calles**. El fondo se conserva al
   alternar Tabla / Mapa dentro de la misma tabla, no después de recargar.

El detalle (⋯) contiene descargas, versiones, historial y selección de contornos.
La columna **KMZ / KML** admite ambos formatos (KMZ hasta 20 MiB, KML hasta 16 MiB)
y guarda y descarga el archivo original tal cual. Un KMZ o KML con un único contorno
válido se activa al terminar. Con varios candidatos
requiere elegir y activar en el detalle. Un reemplazo inválido conserva el
contorno anterior. Un terreno con contorno activo puede verse sin X/Y.

[Guía de inicio del portal](reports/team-a-free-pilot-2026-10-12/GUIA_DE_INICIO.md).
La evidencia local y alojada de las mejoras está en los PR
[#33](https://github.com/Andre07-hash/ARA-MAP/pull/33),
[#34](https://github.com/Andre07-hash/ARA-MAP/pull/34) y
[#35](https://github.com/Andre07-hash/ARA-MAP/pull/35).

## Datos y archivos

- **Render Free** ejecuta `python -m server.hosted`.
- **Neon Postgres** guarda cuentas, accesos, filas, revisiones y metadatos.
- **Supabase Storage privado** guarda los bytes de PDF, JPG, KMZ y KML.
- Los datos y archivos alojados no dependen del disco de Render.
- La ejecución local usa SQLite y almacenamiento local, separados del sitio.

Los PDF y KMZ se adjuntan a filas existentes. En la tabla, el menú ⋯ ofrece
«Exportar a Excel» (la vista con sus filtros) y, para administradores,
«Importar Excel», que agrega filas nuevas a una base tras una revisión previa.
La importación Excel/CSV antigua alimenta bases heredadas y **no** la tabla
maestra. `scripts/cargar_maestra.py` hace la misma carga desde la terminal; es
una operación del responsable con un destino explícito, no un comando para
ejecutar contra el sitio por defecto.

En los archivos de ARA, **X es latitud e Y longitud**. Los valores se guardan
como vienen; superficies y precios no se convierten ni se calculan. Los precios
son MXN. Un dato que falta queda vacío, no en cero.

## Ejecutar y comprobar en desarrollo

Python 3.9 o superior para la app local; Render usa Python 3.12.15. El frontend
es JavaScript sin framework ni paso de build. `vendor/python/` incluye openpyxl
para el uso local. Node.js se usa para pruebas de JavaScript.

```bash
python3 scripts/cuentas.py --sqlite /tmp/ara-dev.db crear dev_admin "Admin local" --rol admin
ARA_MAP_DB=/tmp/ara-dev.db python3 -m server.app
```

La contraseña se pide de forma oculta; es obligatoria, sin longitud mínima.
Abre `http://localhost:8420`. Usa datos ficticios. La guía de desarrollo explica
cómo crear un operador local y concederle una base.

```bash
./verificar.sh
python3 -m unittest tests.test_hosted
node --test tests/js/*.test.mjs
```

Sin zsh, ejecuta los pasos equivalentes de la guía. CI prueba JavaScript y
Python con Postgres desechable. Una prueba local o CI verde no demuestra por sí
sola el comportamiento publicado.

## Publicación y operación

La publicación es **manual en Render**, desde un SHA de `main` revisado y con
CI verde. Auto-deploy está apagado. Una fusión no publica automáticamente.
Se conservan los recursos, los datos y los planes gratuitos, sin tarjeta ni pagos.

El acceso al repositorio permite desarrollar y abrir PRs; no incluye las cuentas
de Render, Neon o Supabase ni sus credenciales. Esos accesos los administra el
propietario. No se necesitan credenciales alojadas para desarrollar localmente.

Un respaldo completo reúne un dump de Postgres y los archivos correspondientes
exportados fuera del host y del bucket activo. La secuencia documentada es
`verificar_archivos.py` → `restaurar_archivos.py` → verificación final de tamaño
y SHA-256, en destinos nuevos para restaurar. Consulta las secciones 7 y 8 del
[checklist de operación](reports/team-a-free-pilot-2026-10-12/OPERATOR_CHECKLIST.md).
Ese documento conserva el contexto histórico de preparación; su encabezado no
significa que la publicación actual siga pendiente.

El servicio gratuito puede tardar en despertar y el almacenamiento tiene cupo
limitado. Cambios de código no recrean los recursos ni cargan los datos locales.
Los adaptadores y reportes de Vercel permanecen como antecedentes; el flujo
vigente utiliza Render. El catálogo público no es requisito actual.
