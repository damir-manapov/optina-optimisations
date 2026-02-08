#!/bin/bash
set -e

echo "=== Python: Formatting ==="
uv run ruff format .

echo ""
echo "=== Python: Linting ==="
uv run ruff check .

echo ""
echo "=== Python: Type checking ==="
uv run pyright .

echo ""
echo "=== TypeScript checks ==="
cd benchmarks
pnpm format
pnpm lint
pnpm typecheck
pnpm test
cd ..

echo ""
echo "=== Check passed ==="
