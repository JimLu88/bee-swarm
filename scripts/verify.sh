#!/usr/bin/env sh
set -e
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
echo "=== H-SEMAS verify ==="
echo "Root: $ROOT"

echo ""
echo "[1/3] Backend unittest ..."
(cd "$ROOT/backend" && python -m unittest discover -s tests -v)

echo ""
echo "[2/3] Frontend eslint (next lint) ..."
(cd "$ROOT/frontend" && npm run lint)

echo ""
echo "[3/3] Frontend next build ..."
(cd "$ROOT/frontend" && npm run build)

echo ""
echo "=== OK verify ==="
