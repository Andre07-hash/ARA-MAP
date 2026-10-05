# Developer handoff: add CSV imports to ARA Map

Prepared September 23, 2026. This is an implementation specification based on the current source code. CSV support has **not** been implemented or tested by this report.

## 1. Requested outcome

Allow users to select a `.csv` file wherever they can currently select an Excel workbook: both **Importar base** and **Agregar a una base existente**. Imported CSV records must support the same terrain details, validation, map display, saved maps, comparison, conflict resolution, and Excel export as Excel-imported records.

Preserve `.xlsx` and `.xlsm` support. Keep the preview → user confirmation → commit flow. One CSV represents one database or one batch appended to a database; CSV has no worksheets. Adding CSV export, reconstructing multiple databases from one CSV, and changing the comparison algorithm are outside this request.

The parsing decisions below are recommended implementation requirements, rather than claims about functionality the application already provides.

## 2. What currently prevents CSV imports

All paths below are relative to `/Users/andrejasso/Desktop/ARA Map`.

| File / symbol | Current behavior | Required change |
| --- | --- | --- |
| `web/components/bases/ImportDialog.js`, `pickWorkbook` | File input accepts only `.xlsx,.xlsm`; both import actions use it. | Add `.csv` and collect the CSV numeric convention described below. |
| `web/lib/api.js`, `previewWorkbook` | Sends raw bytes and URL-encoded filename in `X-Archivo`; checks configured size limit. | Preserve transport and limit checks; optionally send CSV numeric convention. |
| `server/api/importar.py`, `_read_upload` | Rejects extensions other than `.xlsx/.xlsm`, writes a temporary `.xlsx`, calls `read_workbook`. | Dispatch CSV to a CSV reader; retain the workbook branch and cleanup. |
| `server/importer.py`, `read_workbook` | Uses `openpyxl`, chooses a worksheet, maps headers, builds normalized records. | Add CSV reading and reuse row normalization and validation contracts. |
| `server/normalize.py`, `to_number` | Removes commas and `%` before converting to a number. | Do not pass CSV numeric text through this unchanged; decimal commas and percentage text need explicit interpretation. |
| `server/staging.py` | Keeps previews in memory locally; serializes pending imports to Postgres in cloud mode. | Ensure CSV results survive both storage paths and retain single-use tokens. |
| `ImportDialog.js`, `BaseGallery.js`, `README.md` | Copy describes Excel files and worksheets. | Describe all three extensions and a CSV-specific source label. |

The shared API upload ceiling is `25 * 1024 * 1024` bytes. `server/app.py` also limits local request bodies. `api/index.py` advertises and enforces a cloud ceiling of `4 * 1024 * 1024` bytes. These limits apply to CSV too; adding a new extension must not bypass them.

## 3. Accepted CSV contract

### File, encoding, and structure

Required initial support:

- Extension `.csv`, case-insensitive, including filenames with accents or spaces.
- UTF-8, with or without a byte-order mark. Decode strictly using `utf-8-sig`; never use decoding with `errors="ignore"` or `"replace"`.
- Comma or semicolon separators; LF and CRLF line endings.
- Standard quoted fields: separators inside quotes, doubled quotes, and embedded newlines.
- First nonblank record is the header. Ignore genuinely blank records before and after it, while retaining meaningful source line numbers.
- Optionally recognize an exact first nonblank Excel separator directive, `sep=,` or `sep=;`, before the header. If supported, test it and exclude it from terrain counts.
- A file containing only the `Terreno` column is valid. Optional columns must not become mandatory merely because delimiter detection cannot identify a separator.

Other encodings, such as Windows-1252 or UTF-16, can initially produce a clear error asking the user to export **CSV UTF-8**. Do not claim support for all Excel CSV encodings. Automatic legacy-encoding guessing is not necessary for this change.

Use Python's standard-library `csv` module with a newline-preserving text stream, for example `io.StringIO(decoded_text, newline="")`. Do not split on commas, semicolons, or line breaks manually. Do not add pandas or convert CSV into a temporary Excel workbook.

Determine the delimiter using restricted candidates `,` and `;`, header recognition, and consistent field counts. `csv.Sniffer` can assist but is not sufficient by itself. Validate the chosen dialect against the actual file. If candidates produce materially different valid interpretations, reject with a helpful message rather than guessing. Recognize the legitimate one-column case separately. Unquoted delimiters inside values are malformed input, not an invitation to shift columns.

Set `strict=True` when constructing the CSV reader and translate parsing/field-size errors into readable import errors. Delimiter-selection logic must not treat a sample cut halfway through a quoted multiline field as proof the complete file is malformed.

### Headers and terrain fields

Reuse `COLUMN_ALIASES`, `fold`, and the existing domain field names. Column order does not matter. `Terreno`, or an existing recognized alias such as `Nombre` or `Predio`, remains the only required field.

Recommended template:

```csv
ID,Terreno,Estado,Municipio,Dirección,Superficie m2,Superficie Ha,Afectaciones %,Afectaciones m2,Asking Price,Asking $/m2,X,Y
1,Predio Prueba Norte,Estado de México,Tecámac,"Av. Central 120, Colonia Centro",25000,2.5,10%,2500,12500000,500,19.713,-98.968
2,Predio Prueba Sur,Jalisco,Tala,Camino Rural 8,40000,4,0,0,12000000,300,20.653,-103.701
```

These are fictional testing records. Preserve the project's intentional coordinate convention: **X = latitude; Y = longitude**. Do not apply the usual GIS X/Y convention. `Latitud`/`Longitud` and other existing aliases should work identically.

Keep unknown named columns in `TerrainRecord.extra` and show them in preview. For CSV, reject duplicate normalized header labels that would overwrite one another in `extra`. Distinct aliases claiming the same domain field can follow the existing rule: first recognized field wins, second becomes an extra column, visibly reported. Reject nonempty data under an unnamed header rather than silently dropping it. Leave existing Excel header behavior unchanged unless separately covered by regression tests.

### Numeric conventions: prevent silent changes to values

Current `to_number` removes every comma: a CSV value `19,4326` would become `194326`. It also turns `10%` into `10`, while `server/validation.py` expects `0.10` for ten percent. A file-picker change alone would therefore be insufficient even if CSV could reach this function.

For CSV files, provide a compact **Formato de números** choice before requesting preview:

| Choice | Decimal mark | Optional thousands grouping | Examples |
| --- | --- | --- | --- |
| `Punto decimal (1234.56)` — default | `.` | `,` in valid groups of three | `1234.56`, `"1,234.56"` |
| `Coma decimal (1234,56)` | `,` | `.` in valid groups of three | `1234,56`, `1.234,56` |

The delimiter and numeric convention are independent: semicolon does not automatically mean decimal comma. Display the selected convention in the preview. If the user changes it, request a fresh preview and use the new token. Never reuse a token that reflects different parsing settings.

Add an optional query parameter such as `csv_decimal=dot|comma` to the existing preview endpoint. Default absent values to `dot`; reject unknown values for CSV. Preserve `base_id` when adding this parameter. Keep Excel behavior unchanged.

Implement a CSV-specific numeric adapter that validates separator placement **before** converting to a float or forwarding a canonical numeric value to `_build_record`. Do not globally change `to_number` as a shortcut: it is shared with existing workflows. Keep original invalid text available for `ParseNote` and the displayed finding.

Required rules:

- `"1,234.56"` in dot mode becomes `1234.56`; `1.234,56` in comma mode becomes `1234.56`.
- In dot mode, `19,4326` is invalid grouping and must be reported, not converted to `194326`.
- Some values, such as `1,234`, are inherently ambiguous. Interpret them according to the visible, user-selected convention; do not guess individually per cell.
- In `Afectaciones %` only, an explicit percent suffix divides the parsed number by 100: `10%` → `0.10`, `0.5%` → `0.005`. An unsuffixed `0.10` stays `0.10`. Unsuffixed `10` stays `10` and receives the existing fraction-format warning; do not silently divide it.
- Reject `%` in other numeric fields as invalid input. Support the existing `$` notation for monetary fields without allowing arbitrary embedded characters or malformed grouping.
- Preserve negative longitude, numeric zero, empty cells, and existing missing-data findings for `SD`, `N/A`, and related sentinels.
- Reject non-finite values (`NaN`, infinities) before they can reach JSON or persistence. Scientific notation may be accepted if its mantissa follows the selected convention and the final value is finite.
- `ID` must be a finite integer or absent; a fractional or invalid ID must not be silently truncated. Report it and import the named terrain with `id_origen=None`. Matching must continue using existing terrain identity rules, not this source ID.
- Formula-looking content is literal CSV text, never executable input. Numeric formulas must produce a parsing finding rather than evaluation.

Where invalid numeric values are allowed through as missing values, retain the named terrain and expose the finding exactly as the Excel validation workflow does. Coordinate validation must still decide whether it can appear on the map.

### Row accounting and failures

Keep the invariant `filas_con_datos == len(records) + len(rechazadas)` after a structurally valid file is parsed. Skip wholly blank records. Retain `SIN_NOMBRE` rejection details for nonblank rows without a terrain name.

For CSV, require every nonblank data record to have the header's field count, including explicitly empty trailing cells. A count mismatch should fail the file with expected/actual counts and its source line; do not truncate, pad, or shift fields silently. This policy keeps structural failures distinct from named terrains with bad numeric cells.

For quoted multiline records, `fila` should identify the **first physical line** of the record. Capture the reader's previous `line_num + 1` before reading it; do not use the ending line number. Account for skipped blank lines and any `sep=` directive. Explain “línea del archivo CSV” where appropriate in the UI.

An empty, header-only, or all-rejected file must return a useful error and create no base or terrain records. No partially parsed file should produce a confirmable preview after an unrecoverable syntax error.

## 4. Implementation approach

1. Add a CSV reader, either in `server/importer.py` or a focused `server/csv_importer.py`, returning the existing `ImportResult` contract. Use a signature resembling `read_csv_bytes(content: bytes, *, decimal_mode: str = "dot") -> ImportResult`.
2. Reuse header aliases, `_build_record`, `TerrainRecord`, `RejectedRow`, and `ParseNote`. Extract a small shared row-building helper if needed instead of copying the importer. CSV-specific numeric preprocessing must preserve notes and original bad values; consider a narrowly scoped converter callback to avoid forcing text through Excel normalization again.
3. Keep `ImportResult.hoja` a string. For CSV set it to the explicit sentinel `"CSV"`; this avoids a database migration just to support a format without worksheets. Keep the original `.csv` filename in existing provenance fields.
4. In `_read_upload`, validate size first, decode the filename as today, then dispatch on its suffix. The CSV branch can parse raw bytes directly; the Excel branch continues using the existing temporary-file lifecycle. Catch expected CSV/decode errors and convert them to the existing `WorkbookError`/`ApiError` interface. Do not swallow unexpected programming exceptions as invalid files.
5. Retain the existing preview response keys. Add `formato: "csv" | "xlsx" | "xlsm"` and, for CSV, `csv_decimal`, to make UI labels explicit. These can be derived during preview without modifying `ImportResult` or the staging schema. Do not infer CSV solely from a worksheet named `CSV`, because an Excel workbook could legitimately have that name.
6. Keep `validate_all`, `_clasificar`, `confirm`, and `append` as the shared downstream pipeline. Store the already-normalized CSV result under the existing token; confirmation must not reinterpret the file or parse it with different settings.
7. Check `server/staging.py` carefully: local memory tests alone are insufficient. Cloud mode JSON-serializes the dataclasses and reconstructs them with `_decode_pending`. If adding dataclass fields becomes necessary, give them backward-compatible defaults and test decoding existing pending payloads. The minimal approach above needs no new database columns.
8. Update both import and append UI flows. In addition to findings, append preview should show CSV rejected rows and unrecognized-column notices: currently its content does not include the same `Summary`/`RejectedRows` presentation as a new import.
9. Preserve authentication, same-origin checks, request-size enforcement, transaction boundaries, deduplication, conflict choices, and token expiry/consumption. Preview may create temporary cloud staging data; it must not create or mutate persistent bases, terrains, or maps.

## 5. User-facing copy and documentation

Use Spanish to match the application:

- File support: `Archivos admitidos: Excel (.xlsx, .xlsm) y CSV (.csv).`
- CSV hint: `La primera fila debe contener los encabezados. Incluye Terreno y, para ubicarlo en el mapa, X (latitud) e Y (longitud).`
- CSV preview description: `nombre.csv · CSV · punto decimal` or `coma decimal`; never `hoja «undefined»` or a claim that CSV has worksheets.
- Unsupported type: `Formato no admitido. Selecciona un archivo .xlsx, .xlsm o .csv. Si usas Numbers, expórtalo a Excel o CSV UTF-8.`
- Encoding: `No se pudo leer la codificación del CSV. Vuelve a exportarlo como CSV UTF-8.`
- Required header: `El CSV no contiene la columna obligatoria «Terreno».`
- Width error: `El CSV tiene 14 columnas en la línea 7; se esperaban 13. Revisa las comillas y los separadores.`
- Numeric finding: include field, original value, source line, and selected number convention.

Update README import instructions to distinguish the preferred Excel worksheet name from the CSV header requirement. Document UTF-8, quoting, comma/semicolon separators, the numeric-format choice, coordinate convention, and existing local/cloud size limits. Update the gallery's initial instructions and any other Excel-only import labels found by searching `.xlsx`, `workbook`, and `hoja` in the import UI.

Provide a small fictional CSV template with the feature, using the example above. Keep exported maps in Excel format, including the existing sheet-per-database comparison export.

## 6. Required verification

Add focused automated tests using fictional fixtures and temporary databases. Do not point tests at `datos/ara_map.db` or the production Postgres workspace.

| Area | Required cases and expected result |
| --- | --- |
| Basic reader | Comma and semicolon; UTF-8 with/without BOM; `.CSV`; LF/CRLF; accented names and `Dirección`; reordered aliases. Correct mapped values. |
| Quoting | Quoted address containing a comma; escaped quotes; quoted multiline address. Correct field boundaries and physical source line. Existing `clean_text` whitespace normalization is acceptable. |
| Minimal files | Only `Terreno` header plus one name succeeds as an unlocated terrain. Empty/header-only/no-name files fail clearly. Blank records are not counted. |
| Headers/shape | Missing required header; duplicate labels; data under unnamed headers; too few/many fields; malformed quotes. Clear error, no persistent import. |
| Numbers | Both numeric modes; quoted grouping; invalid grouping; signed longitude; zero; `SD`; explicit percent versus fraction; invalid/fractional ID; non-finite values. No silent changes in scale. |
| Findings | Mixed named, nameless, missing-coordinate, invalid-coordinate, and invalid-numeric rows. Accepted/rejected/located counts reconcile; findings retain original text. |
| API dispatch | Real CSV accepted; fake Excel renamed `.csv` rejected; CSV renamed `.xlsx` gets an Excel error; unsupported suffix rejected; non-UTF-8 fails usefully. |
| Preview/confirm | Preview changes no bases/terrains/maps. Confirmation creates exactly the previewed records. Cancel does not import. Reused/expired token fails as before. |
| Append | CSV into an Excel-created base and Excel into a CSV-created base. Duplicate omission and retain/update conflict choices remain correct. |
| Staging | JSON serialization/deserialization round trip retains records, extras, parse notes, rejected rows, line numbers, and findings. Exercise cloud staging behavior with mocks or a disposable test database, including consume-once behavior. |
| Limits/access | Local 25 MiB and cloud 4 MiB checks remain in client and server. Cloud anonymous preview/confirmation is rejected; authenticated import works under existing policy. |
| Map/comparison | CSV base displays expected markers and details; missing-coordinate terrain remains in data. Save/reopen a map; compare against another base; export to Excel with correct per-base worksheets. |
| Regression | Existing `.xlsx` and `.xlsm` paths remain functional; Excel worksheet selection, preview counts, and append classifications are unchanged. |

Place reader tests in `tests/test_csv_importer.py` or extend `tests/test_importer.py`; extend `tests/test_api.py`, `tests/test_cloud.py`, and staging tests as appropriate. Existing `tests.support.TempDatabase` is the local isolation pattern, but ensure cloud database environment variables are disabled or mocked too: a temporary SQLite path alone is not evidence that cloud calls are isolated.

Run the established checks from the project root after implementation:

```sh
python3 -m unittest discover -s tests -t .
node --test tests/js/*.test.mjs
./verificar.sh --todo
```

The last script does not itself execute browser tests; it prints how to run them. Extend and run the browser checks under `tests/e2e` against a disposable local database, following `tests/e2e/README.md`. Verify both file-picker entry points and the decimal-format choice through the actual UI. Report skipped checks explicitly rather than describing them as passed.

For an Excel-versus-CSV equivalence test, generate both fixtures from the same explicit canonical terrain values. Assert equality of normalized values and matching results, excluding source-specific metadata. Include a percentage formatted as `10%` in CSV and stored as numeric `0.10` in Excel.

## 7. Completion criteria and assignment for the developer

The change is ready when a user can select a UTF-8 CSV, preview its interpreted values and findings, import or append it, and use the resulting terrain database in all existing map and comparison workflows. Excel imports remain supported. Malformed CSV cannot silently shift columns or change decimal/percentage scale. Both local and cloud staging and limits are covered by verification.

Suggested assignment to paste to the implementing associate:

> Implement CSV import support in ARA Map according to this report. Support both new database imports and appending to existing databases. Reuse the current preview, confirmation, validation, matching, persistence, and map workflows. Preserve Excel support. Add robust UTF-8 CSV parsing, comma/semicolon delimiters, explicit numeric conventions, correct percentage interpretation, actionable errors, and complete row accounting. Update Spanish UI copy, documentation, and a fictional CSV template. Verify local and cloud behavior using isolated test resources. Deliver the changed files and test results; do not deploy or modify production data as part of this implementation.
