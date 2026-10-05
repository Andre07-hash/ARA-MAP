# MapTest upload pack

36 files: MapTest1–MapTest36. There are 13 Excel workbooks and 23 CSV files.
All terrain names, prices and records are fictional. The coordinates are only illustrative points.

1. Open TEST_MATRIX.md to choose a scenario. MapTest1.xlsx is the baseline.
2. Use a test copy of ARA Map. Upload one file at a time from Bases → Importar archivo.
3. Leave AI disabled to reproduce this review. Turn off “Recordar este formato” when confirming and use a clean test workspace without remembered formats; otherwise previous files can influence detection.
4. Compare the preview and actual saved records with the matrix and manifest.json. Files 30 and 31 are deliberately malformed/empty. Files 27 and 28 deliberately use unsupported encodings.
5. Give DEVELOPER_REPORT.md and this entire pack to the developer. It includes reproduction scripts, evidence and five failing regression cases with two passing controls.

Do not infer that an HTTP 200 or an Importar button means values are correct. MapTest20 and MapTest22 demonstrate successful confirmations with wrong data.

The review changed no application code and used no production data or paid AI. Read the report for the exact test scope and remaining compatibility gaps.
