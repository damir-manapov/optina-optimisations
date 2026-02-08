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

- Python 3.11+ with [uv](https://github.com/astral-sh/uv)
- [Terraform](https://terraform.io/downloads) >= 1.0
- Cloud credentials (see [terraform/README.md](terraform/README.md))

### Setup

```bash
# Install Python dependencies
uv sync

# Set cloud credentials (Selectel example)
export TF_VAR_selectel_domain="123456"
export TF_VAR_selectel_username="your-username"
export TF_VAR_selectel_password="your-password"
export TF_VAR_selectel_openstack_password="your-openstack-password"

# Initialize Terraform
cd terraform/selectel && terraform init && cd ../..
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
