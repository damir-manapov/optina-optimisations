#!/bin/bash
set -e

cd "$(dirname "$0")"

echo "=== Terraform Format & Validate (Selectel) ==="
if [ -d "selectel" ]; then
    (cd selectel && terraform fmt && if [ -d ".terraform" ]; then terraform validate; else echo "Not initialized, skipping validate"; fi)
fi

echo ""
echo "=== Terraform Format & Validate (Timeweb) ==="
if [ -d "timeweb" ]; then
    (cd timeweb && terraform fmt && if [ -d ".terraform" ]; then terraform validate; else echo "Not initialized, skipping validate"; fi)
fi

echo ""
echo "=== TFLint (Linting & Best Practices) ==="
if ! command -v tflint &> /dev/null; then
    echo "tflint not installed. See README.md for installation instructions."
    exit 1
fi
tflint --init
tflint --recursive

echo ""
echo "=== Trivy (Security Misconfigurations) ==="
if ! command -v trivy &> /dev/null; then
    echo "trivy not installed. See README.md for installation instructions."
    exit 1
fi
trivy config --severity HIGH,CRITICAL .

echo ""
echo "=== Terraform Check Passed ==="
