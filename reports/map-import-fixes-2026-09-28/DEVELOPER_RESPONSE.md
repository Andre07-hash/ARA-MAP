# Response to the varied-layout import review — F1–F5 corrected

Date: September 28, 2026. Answers `reports/map-import-tests-2026-09-28/DEVELOPER_REPORT.md`.

**All five defects are fixed.** The seven supplied focused regressions now pass unmodified
(previously two controls passed and five failed), the 36-file matrix moves from 20 to 25 files at
the expected outcome, and the seven files in your "additional capability gaps" table are the only
ones still short of their manifest — exactly as you scoped them.

Supplied fixtures were not touched: all 36 hashes in `evidence/FIXTURE_HASHES.json` still match,
and `evidence/results.json` is byte-identical to the one you delivered
(`58ebc70e81e6…`). This response keeps its own evidence in
`reports/map-import-fixes-2026-09-28/evidence/`.

## Verification

| Check | Result |
|---|---|
| Your focused regressions | `7/7 OK` (was 5 failures) — `evidence/regressions-after-fixes.txt` |
| Ordinary Python suite | **605 tests OK**, 21 skipped (was 545, 20 skipped) |
| Same suite on macOS system Python 3.9.6 | OK |
| JavaScript unit tests | 62 OK |
| Browser suite (`tests/e2e`, real Chrome) | **65/65 checks, no console errors** (was 62 checks) |
| ruff / mypy | clean / no issues in 39 source files |
| Coverage | 94% total; `filas.py` 100%, other touched modules 91–98% |
| Disposable Postgres | `tests/test_postgres` + `tests/test_postgres_aceptacion`, 21 tests OK |
| 36-file matrix | 25 PASS, 6 MISMATCH, 1 UNRESOLVED, 4 REJECTED — `evidence/matrix-after-fixes.txt` |
| Paid usage rows across the matrix | 0 |

The browser run used a throwaway SQLite file and its own port; the Postgres run used a temporary
local cluster in a scratch directory, created and destroyed for the run. Production, Neon and the
normal local database were not touched, and no AI provider was configured or called.

Eleven of the 82 files in your `SOURCE_SNAPSHOT.json` changed, plus one new module
(`server/asistente/filas.py`). The other 71 are untouched; the list is in *What changed* below.

## F1 — Excel currency formatting is discarded (P1)

**Before:** `MapTest20.xlsx` imported four terrains labelled "en MXN", `FICTICIO Encino` with
`asking_price=1200000.0`, no questions.
**After:** four terrains, `con_precio=0`, every `asking_price` null in the preview *and* in the
stored records; the amount is kept as additional data with its original figure.

The value pass of the workbook reader now reads cells instead of bare values, so each cell's
`number_format` is available. `campos.moneda_formato` reads only a format's *literal* text — quoted
runs (`"USD "#,##0.00`), the symbol of a `[$…-…]` section, backslash escapes — and matches it with
the same `_MONEDA` table that reads headers and cell text. The numeric pattern itself never matches,
so `#,##0.00`, `0.00%`, `0.00" ha"` and date formats declare nothing, and a bare `$`, `[$$-409]` or
`"MXN "` stays the peso.

`Hoja` carries the result per cell as `(row, column, ISO code)`, only for cells that both hold a
value and declare a foreign currency, so an ordinary peso file stores nothing. Beyond
`MAX_MONEDAS` (5 000) the column and code are remembered instead of the cell, and such a column
counts as carrying the currency throughout — a sheet too large to record cell by cell must not look
free of evidence. The field is in the packed draft on both sides (`asdict` and the explicit
`desempaquetar` reconstruction), and `PARSER_VERSION` moved to 2, so a draft made by the old parser
is asked to be analysed again rather than read with the field missing.

From there the evidence flows through the checks you already had: `Columna.monedas` merges header
text, cell text and cell formats; `detectar._moneda_extranjera` sets the column back to additional
data whoever chose it (name, alias, **saved format**, automatic proposal); `campos.respaldo` refuses
it as a price; and `plan.construir` refuses again, so an explicit user override returns an error
instead of a preview. No generic price question is asked about such a column —
`_preguntas_desconocidas` skips columns with a currency.

Mixed currencies inside one column are named, not collapsed: `Columna.monedas` is a tuple and the
message reads "está en USD y EUR". One foreign-formatted cell among pesos blocks the whole column,
which is the rule your header/text path already stated.

Because the amounts look like bare numbers on screen, the message says where the currency was read:
*"«Precio» está en dólares según el formato de celda de Excel. …se conserva como dato adicional con
su importe original."* The preview carries a `monedas_extranjeras` list and shows it above the rows;
the interpretation payload carries `monedas` and `monedas_formato` per column.

**Covered by:** `tests/test_asistente_monedas.py` (25 tests) — format parsing including EUR, mixed
cells, bare-dollar and MXN controls, peso files still importing at full price, the packed-draft
round trip, an older draft without the field, an explicit override refused, a remembered format
unable to bring the column back, and stored records checked after `confirmar`. Browser: *"dollars
declared only by the cell format never become MXN"*, which also asserts the stored rows through the
API. Postgres: `test_currency_and_row_decisions_survive_a_serialized_draft`.

## F2 — a real terrain beginning with "Total" is removed (P1)

**Before:** `MapTest22.csv` imported three terrains; `Total FICTICIO Encino` was marked `TOTALES`.
**After:** four terrains, no exclusions. `MapTest7.csv` still excludes its genuine `TOTAL` row.

Row classification moved into a new module, `server/asistente/filas.py`, and a name is now only
grounds for *looking*. A totals-like label is a summary when the row also:

1. **identifies no single property** — no readable latitude *and* longitude pair, and nothing in
   estado, municipio, dirección or id de origen; and
2. **behaves like a total** — at least one summable mapped column (price, m², ha, affected m²)
   equals the sum of the ordinary rows within 0.5%, *or* the name is exactly a summary word.

`MapTest7`'s row matches on the sum (`12 250 000` and `24 500`); `MapTest22`'s row has coordinates,
so it is a terrain. `Total`, `Subtotal` and `Total general` are accepted as real names when the row
carries terrain evidence. Where the evidence is thin the row is **kept**, not dropped: a
totals-looking name whose figures do not add up and which has no location is imported, because the
exclusion would be the damage. The one exception is an exact summary word with no terrain data at
all, which stays excluded — and is restorable, see F5.

**Covered by:** `tests/test_asistente_filas.py` (19 tests), including the summary-with-a-municipality
case, the figures-that-do-not-add-up case, and the repeated-header control.

## F3 — tab-separated CSV accepted as a one-column list (P2)

**Before:** `MapTest29.csv` became four names such as
`FICTICIO Encino 1200000 2400 19.4326 -99.1332`.
**After:** five columns, four terrains with price, area and coordinates, zero questions, `PASS`
against your manifest.

`DELIMITERS` is now `(",", ";", "\t")` in `server/csv_importer.py`, and the `sep=` directive accepts
a tab. `rejilla._lecturas_plausibles` was generalized from exactly two readings to any number: the
readings that agree cell for cell are one table (a single-column name list still reads the same
three ways and is *not* rejected), then a reading that splits into columns wins over one that does
not, then a reading that is the same width throughout wins, and only a genuine tie is offered as a
choice. The sheet/separator labels in the question and in the UI gained "Tabulaciones".

**Covered by:** `tests/test_asistente_lectura.py` — the tab table, the tab directive, comma and
semicolon controls, a one-column name list, quoted multiline values with their line numbers, a tab
*inside* a comma file that must not take over, the legacy `read_csv_bytes` path, and an end-to-end
preview-and-import. `MapTest26` and the existing CSV cases stay green.

## F4 — a header after row 50 cannot be selected (P2)

**Before:** `MapTest35.xlsx` had no usable preview through the guided route.
**After:** `PASS` with **zero** questions and four correct terrains, and the row is reachable by hand.

Two changes. First, the automatic search is still bounded to the first 50 rows, but when *none* of
them looks like a header — a page of notes, a title page — it widens to 2 000 rows instead of
settling for row 1. That alone finds `MapTest35`'s header at physical row 56 and puts it first in
the offered list. Second, the correction panel no longer depends on that list being long enough: it
has an **"Otra fila del archivo"** number field where the manager types **the row number printed in
the file**. The server translates it against the sheet's retained rows (`servicio._indice_de_linea`),
so blank rows cannot make the displayed number and the internal index disagree, and a row that has
no data is refused by name with the nearby rows that do. The field states the file's real range and
rejects a number outside it before sending anything.

**Covered by:** `tests/test_asistente_lectura.py` — the late header found automatically, a header in
the first rows still winning, blank rows keeping printed numbers honest, naming a row by its printed
number through the API, the refusal for an empty row, and the offered rows carrying the user-visible
number. Browser: *"a header below a page of notes is found, and named by its printed row"*.

## F5 — a footer becomes a terrain, with no row control (P2)

**Before:** `MapTest23.csv` offered five terrains; the note was the fifth; the browser had no way to
remove it.
**After:** four terrains. The note is listed as set aside with its reason, and the preview can put it
back.

A footer is recognized by evidence too: it must be **the only thing written on its line** *and* its
name must announce itself (`NOTA`, `AVISO`, `OBSERVACIONES`, `FUENTE`, `ACTUALIZADO`…). `Nota Verde`
with a price and coordinates is a terrain, and a name-only record that is not note-like — `FICTICIO
Sauce,,,,` — is still imported, so this does not repeat F2's mistake.

The row decision is now explicit and durable. `ImportPlan` gained `incluir` beside `excluir`;
`servicio` accepts both as corrections, `fusionar` takes a row off the opposite list when it is named
on one, and `validar` refuses a row that is on both. Preview rows and excluded rows both carry their
`indice`, so the browser can name a row without guessing: every terrain row has **No importar** and
every set-aside row has **Sí es un terreno: importarla**. The decision rides in the plan through
every later correction, the rebuilt preview and the confirmation.

**Covered by:** `tests/test_asistente_filas.py` `Decisiones` — restore then confirm and read the
stored rows, a restored row surviving a later `decimal` correction, removing an ordinary row by its
number, one list taking a row off the other, header rows refused, and a malformed list refused.
Browser: *"a footer is set aside, restored from the preview, and removed again"*, which imports and
then checks the stored rows contain `Total Predio Alfa` and no `NOTA…`.

## The 36 files, before and after

| File | Case | Before | After | Questions | Stored mismatches |
|---|---|---|---|---:|---:|
| `MapTest1.xlsx` | Excel standard control | PASS | PASS | 0 | 0 |
| `MapTest2.csv` | Reordered columns | PASS | PASS | 0 | 0 |
| `MapTest3.csv` | Semicolon and decimal comma | PASS | PASS | 0 | 0 |
| `MapTest4.xlsx` | Title, merged banner and blank rows | PASS | PASS | 0 | 0 |
| `MapTest5.xlsx` | Instructions sheet before terrain sheet | PASS | PASS | 0 | 0 |
| `MapTest6.csv` | Repeated header inside table | PASS | PASS | 0 | 0 |
| `MapTest7.csv` | Summary total row | PASS | PASS | 0 | 0 |
| `MapTest8.xlsx` | Repeated price headers: total and unit | MISMATCH | MISMATCH | 1 | 4 |
| `MapTest9.csv` | English headers | PASS | PASS | 3 | 0 |
| `MapTest10.csv` | Unknown headers require mapping | PASS | PASS | 5 | 0 |
| `MapTest11.xlsx` | Two header rows with units | PASS | PASS | 2 | 0 |
| `MapTest12.xlsx` | Transposed property cards | UNRESOLVED | UNRESOLVED | 5 | 0 |
| `MapTest13.xlsx` | Two side-by-side terrain tables | MISMATCH | MISMATCH | 4 | 3 |
| `MapTest14.xlsx` | Two valid worksheets: choose one | PASS | PASS | 1 | 0 |
| `MapTest15.csv` | Coordinates together in one cell | MISMATCH | MISMATCH | 0 | 8 |
| `MapTest16.csv` | Degrees minutes seconds coordinates | MISMATCH | MISMATCH | 0 | 8 |
| `MapTest17.csv` | Projected UTM coordinates | PASS | PASS | 0 | 0 |
| `MapTest18.csv` | Mixed decimal conventions by column | MISMATCH | MISMATCH | 1 | 4 |
| `MapTest19.csv` | USD stated in header | PASS | PASS | 0 | 0 |
| **`MapTest20.xlsx`** | **USD only in the Excel number format** | **MISMATCH** | **PASS** | 0 | 0 |
| `MapTest21.xlsx` | Native Excel percentage values | PASS | PASS | 0 | 0 |
| **`MapTest22.csv`** | **Legitimate name begins with "Total"** | **MISMATCH** | **PASS** | 0 | 0 |
| **`MapTest23.csv`** | **Footnote below data** | **MISMATCH** | **PASS** | 0 | 0 |
| `MapTest24.xlsx` | Leading blank rows and columns | PASS | PASS | 0 | 0 |
| `MapTest25.csv` | Decimal comma with quoted comma CSV | PASS | PASS | 0 | 0 |
| `MapTest26.csv` | Quotes, comma and multiline extra text | PASS | PASS | 0 | 0 |
| `MapTest27.csv` | UTF-16 Excel CSV export | REJECTED | REJECTED | 0 | 0 |
| `MapTest28.csv` | Windows-1252 CSV export | REJECTED | REJECTED | 0 | 0 |
| **`MapTest29.csv`** | **Tab-delimited file with .csv extension** | **MISMATCH** | **PASS** | 0 | 0 |
| `MapTest30.csv` | Malformed CSV quoting | REJECTED | REJECTED | 0 | 0 |
| `MapTest31.csv` | Empty CSV | REJECTED | REJECTED | 0 | 0 |
| `MapTest32.csv` | Blank price versus real zero | PASS | PASS | 0 | 0 |
| `MapTest33.xlsx` | Price formulas with cached results | PASS | PASS | 0 | 0 |
| `MapTest34.csv` | Table without a header row | MISMATCH | MISMATCH | 5 | 2 |
| **`MapTest35.xlsx`** | **Header after 55 introduction lines** | **UNRESOLVED** | **PASS** | 0 | 0 |
| `MapTest36.csv` | UTF-8 BOM and separator directive | PASS | PASS | 0 | 0 |

Totals: 25 PASS (was 20), 6 MISMATCH (was 10), 1 UNRESOLVED (was 2), 4 clear rejections (unchanged).
The seven files short of their manifest are `MapTest8, 12, 13, 15, 16, 18, 34` — your capability
table exactly, treated as the next scoped plan and not touched here. As you asked: these are
designed boundary cases, not an accuracy benchmark, and no number here is a model score.

## What changed

New: `server/asistente/filas.py` (168 lines) — row classification and the user's row decisions.

Modified: `server/asistente/rejilla.py`, `perfil.py`, `campos.py`, `plan.py`, `detectar.py`,
`servicio.py`, `server/csv_importer.py`, `web/components/import/AssistantViews.js`,
`web/components/import/ImportAssistant.js`, `web/styles/controls.css`, `web/styles/assistant.css`.
Every file stays well under the 800-line limit; the largest touched module is `detectar.py` at 671.

Tests added: `tests/test_asistente_monedas.py` (25), `tests/test_asistente_filas.py` (19),
`tests/test_asistente_lectura.py` (15), one Postgres draft test, three browser checks, and three new
fictional fixtures written by `tests/fixtures/asistente/generar.py`
(`moneda_formato.xlsx`, `nota_al_pie.csv`, `encabezado_tardio.xlsx`). `README.md` documents the new
behaviour in the sections that already covered currency, totals rows, separators and corrections.

## Two things worth your judgement

**A remembered format learns the currency decision.** When a foreign-currency file is imported with
"Recordar este formato" left on, the saved format records that price column as additional data. A
later file with the same headings *in pesos* then arrives without a price until corrected in the
preview. This is not new — a file with `USD` in the header already behaved this way — but F1 makes it
reachable from cell formats too. The safe direction, and correctable in one click, so I left it; say
the word and I will stop such a decision from being remembered.

**A thin-evidence totals row is imported.** By design: `Total de la zona norte` with figures that do
not add up and no location is kept as a terrain. I chose keeping a possible record over deleting a
possible one, since the exclusion is the irreversible-looking outcome for the boss. The preview's
per-row control covers the other direction.

## Not done, deliberately

- The seven capability gaps (`MapTest8, 12, 13, 15, 16, 18, 34`): transposed cards, side-by-side
  table regions, combined and DMS coordinates, per-column numeric conventions, no-header tables, and
  the repeated-price question. Awaiting your go-ahead as a separate plan.
- UTM stays unsupported until CRS-aware conversion is deliberate work.
- UTF-16 and Windows-1252 still fail with the UTF-8 export instruction.
- No production or Neon verification: the Postgres evidence is a disposable local cluster.
