# optina-optimisations

Bayesian optimization for cloud infrastructure configurations using [Optuna](https://optuna.org/).

## Overview

This project automates finding optimal configurations for various products on cloud providers. It deploys infrastructure via Terraform, runs benchmarks, and uses Bayesian optimization to find the best cost-performance trade-offs.

## Optimizers

| Optimizer | Target | Benchmark Tool | Metrics |
|-----------|--------|----------------|---------|
| [optimizers/redis](optimizers/redis/) | Redis cache | memtier_benchmark | ops/sec, p99 latency |
| [optimizers/minio](optimizers/minio/) | MinIO storage | warp | throughput, IOPS |
| [optimizers/postgres](optimizers/postgres/) | PostgreSQL | pgbench | TPS, latency |
| [optimizers/meilisearch](optimizers/meilisearch/) | Meilisearch | k6 | queries/sec |

## Supported Clouds

- **Selectel** - OpenStack-based, ru-7 region
- **Timeweb** - TWC API, ru-1 location

## Quick Start

### Prerequisites

**Required for optimizers:**
- Python 3.11+ with [uv](https://github.com/astral-sh/uv)
- [Terraform](https://terraform.io/downloads) >= 1.0
- Cloud credentials (see [terraform/README.md](terraform/README.md))

**Required for benchmarks:**
- Node.js 20+
- [pnpm](https://pnpm.io/) >= 9.0
- Docker & Docker Compose

**Required for health checks:**
- [gitleaks](https://github.com/gitleaks/gitleaks) - secrets scanning
- [jq](https://jqlang.github.io/jq/) - JSON processing

**Required for Terraform checks:**
- [tflint](https://github.com/terraform-linters/tflint) - Terraform linter
- [trivy](https://github.com/aquasecurity/trivy) - security scanner

### Installation

```bash
# Ubuntu/Debian
curl -LsSf https://astral.sh/uv/install.sh | sh
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
sudo apt install -y nodejs jq docker.io docker-compose-plugin
sudo npm install -g pnpm

# Terraform
wget -O- https://apt.releases.hashicorp.com/gpg | sudo gpg --dearmor -o /usr/share/keyrings/hashicorp-archive-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/hashicorp.list
sudo apt update && sudo apt install -y terraform

# gitleaks
GITLEAKS_VERSION=$(curl -s https://api.github.com/repos/gitleaks/gitleaks/releases/latest | jq -r .tag_name)
wget https://github.com/gitleaks/gitleaks/releases/download/${GITLEAKS_VERSION}/gitleaks_${GITLEAKS_VERSION#v}_linux_x64.tar.gz
tar -xzf gitleaks_*.tar.gz gitleaks && sudo mv gitleaks /usr/local/bin/ && rm gitleaks_*.tar.gz

# tflint
TFLINT_VERSION=$(curl -s https://api.github.com/repos/terraform-linters/tflint/releases/latest | jq -r .tag_name)
wget https://github.com/terraform-linters/tflint/releases/download/${TFLINT_VERSION}/tflint_linux_amd64.zip
unzip tflint_linux_amd64.zip && sudo mv tflint /usr/local/bin/ && rm tflint_linux_amd64.zip

# trivy
sudo apt install -y apt-transport-https gnupg
wget -qO - https://aquasecurity.github.io/trivy-repo/deb/public.key | sudo gpg --dearmor -o /usr/share/keyrings/trivy.gpg
echo "deb [signed-by=/usr/share/keyrings/trivy.gpg] https://aquasecurity.github.io/trivy-repo/deb generic main" | sudo tee /etc/apt/sources.list.d/trivy.list
sudo apt update && sudo apt install -y trivy
```

### Setup

```bash
# Clone and enter repo
git clone https://github.com/damir-manapov/optina-optimisations.git
cd optina-optimisations

# Install Python dependencies
uv sync

# Install TypeScript dependencies (for benchmarks)
cd benchmarks && pnpm install && cd ..

# Set cloud credentials (Selectel example)
export TF_VAR_selectel_domain="123456"
export TF_VAR_selectel_username="your-username"
export TF_VAR_selectel_password="your-password"
# Generate random password for Terraform to create OpenStack credentials
export TF_VAR_selectel_openstack_password="$(openssl rand -base64 24)"

# Initialize Terraform
cd terraform/selectel && terraform init && cd ../..

# Verify setup
./check.sh        # Python linting/types
./all-checks.sh   # Full checks (requires GITHUB_TOKEN for renovate)
```

### Run Optimization

```bash
# Redis - optimize for ops/sec
uv run python optimizers/redis/optimizer.py --cloud selectel --trials 10 --metric ops_per_sec

# MinIO - optimize for throughput
uv run python optimizers/minio/optimizer.py --cloud selectel --trials 10

# PostgreSQL - optimize infrastructure
uv run python optimizers/postgres/optimizer.py --cloud selectel --mode infra --trials 10

# Meilisearch - optimize config
uv run python optimizers/meilisearch/optimizer.py --cloud selectel --mode config --trials 20

# View results
uv run python optimizers/redis/optimizer.py --cloud selectel --show-results
uv run python optimizers/redis/optimizer.py --cloud selectel --export-md
```

## How It Works

1. **Optuna suggests** a configuration (CPU, RAM, disk, software settings)
2. **Terraform deploys** infrastructure on the cloud
3. **Benchmark runs** against the deployed system
4. **Results logged** and Optuna learns from them
5. **Repeat** until trials exhausted or convergence

## Configuration Space

Each optimizer tunes different parameters:

| Optimizer | Infrastructure | Software Config |
|-----------|----------------|-----------------|
| Redis | CPU, RAM, nodes | io-threads, persistence, eviction policy |
| MinIO | CPU, RAM, disk type, nodes | erasure coding |
| PostgreSQL | CPU, RAM, disk | shared_buffers, work_mem, connections |
| Meilisearch | CPU, RAM | indexing threads, max indexing memory |

## Pricing

Cloud pricing is centralized in [pricing.py](pricing.py):
- CPU/RAM/disk costs per cloud
- `cost_efficiency` metric (performance per ₽/month)
- Cloud constraints (min RAM per CPU, disk types)

## Project Structure

```
optina-optimisations/
├── optimizers/           # Bayesian optimizers (main focus)
│   ├── redis/
│   ├── minio/
│   ├── postgres/
│   ├── meilisearch/
│   └── storage/          # Optuna study databases
├── terraform/            # Cloud infrastructure
│   ├── selectel/
│   └── timeweb/
├── benchmarks/           # Database query benchmarks (TypeScript)
│   ├── src/
│   ├── compose/
│   └── package.json
├── docs/                 # Documentation
├── common.py             # Shared Python utilities
├── pricing.py            # Cloud pricing data
└── pyproject.toml        # Python project config
```

## Database Benchmarks

The [benchmarks/](benchmarks/) directory contains a TypeScript suite for benchmarking indexless queries on PostgreSQL, ClickHouse, and Trino+Iceberg. See [benchmarks/README.md](benchmarks/package.json) for details.

```bash
cd benchmarks
pnpm install
pnpm compose:up
pnpm generate -n 10_000_000
pnpm benchmark --report
```

## Development

```bash
# Python checks
./check.sh  # ruff format, lint, pyright

# Full checks
./all-checks.sh
```

## Documentation

- [docs/OPTIMIZERS.md](docs/OPTIMIZERS.md) - Optimizer usage guide
- [docs/OPTIMIZER_GUIDE.md](docs/OPTIMIZER_GUIDE.md) - How to create new optimizers
- [terraform/README.md](terraform/README.md) - Cloud setup instructions
