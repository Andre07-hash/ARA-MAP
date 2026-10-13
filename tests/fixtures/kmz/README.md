# Fictional KML fixtures for `server/kmz.py`

Every name, shape and coordinate in this folder is **invented**. None is a real
terrain, owner, listing or company file. The coordinates are rough rectangles in
open country inside Mexico, chosen only so the location rules can be exercised.

- `*.kml` — the documents. `tests/test_kmz.py` packages each one into a KMZ in
  memory, and builds package-level cases there too (several KML files,
  encryption flag, unsupported compression, truncation, entry and size limits).
- `generar.py` — regenerates the documents: `python3 tests/fixtures/kmz/generar.py`.

Accepting these fixtures is not acceptance against real company KMZ files. Real
samples must be reviewed privately and are never committed.
