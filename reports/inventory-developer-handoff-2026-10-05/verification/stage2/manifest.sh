#!/bin/sh
# Candidate source manifest: sha256 of every file under server/ api/ scripts/ web/
# (excluding api/data/ and __pycache__), sorted by path. Usage: manifest.sh <label>
set -eu
ROOT=$(cd "$(dirname "$0")/../../../.." && pwd)
OUT="$ROOT/reports/inventory-developer-handoff-2026-10-05/verification/runs/CANDIDATE_MANIFEST_stage2_${1:?label}.sha256"
cd "$ROOT"
find server api scripts web -type f ! -path 'api/data/*' ! -path '*/__pycache__/*' ! -name '*.pyc' | LC_ALL=C sort | xargs sha256sum > "$OUT"
echo "$OUT $(wc -l < "$OUT") files, sha256 $(sha256sum "$OUT" | cut -c1-64)"
