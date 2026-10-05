# Independent production confirmation — October 1, 2026

The requested USD release was already deployed by the developer before this verification. No duplicate deployment or database migration was performed.

Production: https://ara-map-ivory.vercel.app

Deployment: `dpl_3vsdvzhV86Y1goinejgcHP83vNML`

Verified directly against production:
- Base 37 and saved map 9 each retain all 79 workbook records, including 59 total prices and 60 per-square-metre prices.
- Names, original IDs, prices, coordinates and square-metre areas match the original workbook record by record, using the unique source order rather than names (some names repeat).
- Every priced record is labelled USD in both the base and saved map.
- The saved-map Excel export contains 79 rows and a currency column; El Dorado retains USD 122.50/m².
- The production browser displays El Dorado as USD 122.50/m². Screenshot: `live-usd-check.png`.

For the presentation, open Bases → **Demo USD · Base Terrenos 09.26 (1 oct 2026)**. Use **Base Terrenos 09.26 copy.xlsx** if demonstrating a fresh import; its numerical precision is greater than the CSV export.

Machine-readable evidence: `independent-live-verification.json`. Verified export: `verified-demo-export.xlsx`.
