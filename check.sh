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
echo "=== TypeScript: Biome check ==="
cd benchmarks
pnpm lint
pnpm check

echo ""
echo "=== TypeScript: Type checking ==="
pnpm typecheck

echo ""
echo "=== TypeScript: Tests ==="
pnpm test
cd ..

echo ""
echo "=== Check passed ==="
